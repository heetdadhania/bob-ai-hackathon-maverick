"""
ml/predict.py

Loads the trained XGBoost model, scores every asset in the feature_matrix
table, computes severity rankings, and writes results to the `risk_scores` table.

Severity formula:
    severity_score = failure_probability × customers_served × criticality_weight

Where criticality_weight maps:
    Tier 1 → 3  (most critical)
    Tier 2 → 2
    Tier 3 → 1  (least critical)

This linear formula makes the ranking directly interpretable as expected impact:
a high-probability failure at a Tier-1 feeder serving many customers scores
highest. Chosen over log1p(customers_served) for transparency in the dashboard.

Run:
    python -m ml.predict
"""

import json
import logging
import os

import joblib
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import xgboost as xgb
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]
MODEL_PATH: str = os.environ["MODEL_PATH"]
SHAP_PATH: str = MODEL_PATH.replace(".json", "_shap_explainer.pkl")
META_PATH: str = MODEL_PATH.replace(".json", "_meta.json")

TOP_N_SHAP_FEATURES: int = 3

# Criticality tier → weight mapping (Tier 1 = most critical)
CRITICALITY_WEIGHTS: dict[int, float] = {1: 3.0, 2: 2.0, 3: 1.0}


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model(path: str) -> xgb.XGBClassifier:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"XGBoost model not found: {path}. Run ml/train_model.py first."
        )
    model = xgb.XGBClassifier()
    model.load_model(path)
    return model


def _load_artifacts() -> tuple[xgb.XGBClassifier, object, list[str]]:
    for artefact_path in (MODEL_PATH, SHAP_PATH, META_PATH):
        if not os.path.exists(artefact_path):
            raise FileNotFoundError(
                f"Required artefact not found: {artefact_path}. "
                "Run ml/train_model.py first."
            )
    model = load_model(MODEL_PATH)
    explainer = joblib.load(SHAP_PATH)
    with open(META_PATH, encoding="utf-8") as fh:
        meta = json.load(fh)
    return model, explainer, meta["feature_cols"]


# ── Prediction ────────────────────────────────────────────────────────────────

def predict_failure_probability(
    model: xgb.XGBClassifier,
    features_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return asset_id + failure_probability for all rows in features_df.

    Validates that all columns the model was trained on are present before
    scoring, so a column-mismatch fails loudly rather than silently using
    wrong feature order.
    """
    with open(META_PATH, encoding="utf-8") as fh:
        feature_cols: list[str] = json.load(fh)["feature_cols"]

    missing = [c for c in feature_cols if c not in features_df.columns]
    if missing:
        raise ValueError(
            f"features_df is missing required model columns: {missing}"
        )
    if "asset_id" not in features_df.columns:
        raise ValueError("features_df must contain an 'asset_id' column")

    feature_matrix = features_df[feature_cols].fillna(
        features_df[feature_cols].median()
    )
    probabilities = model.predict_proba(feature_matrix)[:, 1]

    return pd.DataFrame({
        "asset_id": features_df["asset_id"].values,
        "failure_probability": np.round(probabilities, 4),
    })


# ── Severity ranking ──────────────────────────────────────────────────────────

def rank_by_severity(
    predictions_df: pd.DataFrame,
    assets_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute severity_score and return assets ranked descending.

    severity_score = failure_probability × customers_served × criticality_weight

    criticality_weight: Tier 1 → 3, Tier 2 → 2, Tier 3 → 1.
    Assets with an unknown tier receive weight 1 (least critical, safe default).
    """
    required_pred = {"asset_id", "failure_probability"}
    required_assets = {"asset_id", "customers_served", "criticality_tier"}

    missing_pred = required_pred - set(predictions_df.columns)
    if missing_pred:
        raise ValueError(f"predictions_df missing columns: {sorted(missing_pred)}")
    missing_assets = required_assets - set(assets_df.columns)
    if missing_assets:
        raise ValueError(f"assets_df missing columns: {sorted(missing_assets)}")

    merged = predictions_df.merge(
        assets_df[["asset_id", "customers_served", "criticality_tier"]],
        on="asset_id",
        how="left",
    )
    merged["criticality_weight"] = (
        merged["criticality_tier"]
        .fillna(3)
        .astype(int)
        .map(CRITICALITY_WEIGHTS)
        .fillna(1.0)
    )
    merged["severity_score"] = np.round(
        merged["failure_probability"]
        * merged["customers_served"].fillna(0)
        * merged["criticality_weight"],
        4,
    )

    ranked = (
        merged.sort_values("severity_score", ascending=False)
        .reset_index(drop=True)
    )
    ranked["rank"] = ranked.index + 1
    return ranked


# ── SHAP top-features helper ──────────────────────────────────────────────────

def _compute_shap_top_features(
    explainer: object,
    feature_matrix: pd.DataFrame,
    feature_cols: list[str],
) -> list[list[dict]]:
    shap_values = explainer.shap_values(feature_matrix)
    result: list[list[dict]] = []
    for i in range(len(feature_matrix)):
        shap_row = shap_values[i]
        top_indices = np.argsort(np.abs(shap_row))[::-1][:TOP_N_SHAP_FEATURES]
        result.append([
            {"feature": feature_cols[j], "shap_value": round(float(shap_row[j]), 4)}
            for j in top_indices
        ])
    return result


# ── DB writer ─────────────────────────────────────────────────────────────────

def _write_risk_scores(ranked_df: pd.DataFrame, top_features: list[list[dict]]) -> None:
    rows = [
        {
            "asset_id": row["asset_id"],
            "failure_probability": float(row["failure_probability"]),
            "severity_score": float(row["severity_score"]),
            "top_features": json.dumps(top_features[i]),
            "rank": int(row["rank"]),
        }
        for i, (_, row) in enumerate(ranked_df.iterrows())
    ]

    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:
        raise RuntimeError(f"Cannot connect to Neon Postgres: {exc}") from exc

    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO risk_scores
                        (asset_id, scored_at, failure_probability,
                         severity_score, top_features, rank)
                    VALUES
                        (%(asset_id)s, NOW(), %(failure_probability)s,
                         %(severity_score)s, %(top_features)s::jsonb, %(rank)s)
                    ON CONFLICT (asset_id) DO UPDATE SET
                        scored_at           = NOW(),
                        failure_probability = EXCLUDED.failure_probability,
                        severity_score      = EXCLUDED.severity_score,
                        top_features        = EXCLUDED.top_features,
                        rank                = EXCLUDED.rank
                    """,
                    rows,
                    page_size=100,
                )
        logger.info("risk_scores written: %d assets ranked.", len(rows))
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> pd.DataFrame:
    model, explainer, feature_cols = _load_artifacts()

    # Build live features per asset (latest date) using the same pipeline as training
    from feature_engineering.build_features import (  # noqa: PLC0415
        _load_tables,
        compute_rolling_features,
        _add_incident_features,
        build_training_table,
    )
    sensor_df, assets_df_full, incidents_df = _load_tables()
    features_df = compute_rolling_features(sensor_df)
    features_df = _add_incident_features(features_df, incidents_df)
    training_df = build_training_table(features_df, assets_df_full)

    # For inference use only the most recent row per asset
    inference_df = (
        training_df.sort_values("date")
        .groupby("asset_id", as_index=False)
        .last()
        .reset_index(drop=True)
    )

    from sqlalchemy import create_engine, text  # noqa: PLC0415
    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        assets_df = pd.read_sql_query(
            text("SELECT asset_id, customers_served, criticality_tier FROM assets"),
            conn,
        )

    predictions_df = predict_failure_probability(model, inference_df)
    ranked_df = rank_by_severity(predictions_df, assets_df)

    feat_mat = inference_df[feature_cols].fillna(inference_df[feature_cols].median())
    top_features = _compute_shap_top_features(explainer, feat_mat, feature_cols)

    # Align top_features order to ranked_df (reordered by severity)
    pred_index = {aid: i for i, aid in enumerate(predictions_df["asset_id"])}
    aligned_top_features = [
        top_features[pred_index[aid]] for aid in ranked_df["asset_id"]
    ]

    _write_risk_scores(ranked_df, aligned_top_features)

    logger.info(
        "Predict complete. Top-5 assets by severity:\n%s",
        ranked_df[["rank", "asset_id", "failure_probability", "severity_score"]]
        .head(5)
        .to_string(index=False),
    )
    return ranked_df


if __name__ == "__main__":
    main()
