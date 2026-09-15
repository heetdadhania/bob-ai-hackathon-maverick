"""
ml/train_model.py

Trains an XGBoost binary classifier on the feature_matrix table and compares
it against a logistic regression baseline.

Outputs:
  - Saved XGBoost model at MODEL_PATH (from env)
  - SHAP explainer at MODEL_PATH with _shap_explainer.pkl suffix
  - Feature metadata JSON at MODEL_PATH with _meta.json suffix

Run:
    python -m ml.train_model
"""

import json
import logging
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]
MODEL_PATH: str = os.environ["MODEL_PATH"]
SHAP_PATH: str = MODEL_PATH.replace(".json", "_shap_explainer.pkl")
META_PATH: str = MODEL_PATH.replace(".json", "_meta.json")

RANDOM_SEED: int = 42
TEST_SIZE: float = 0.2
AUC_WARN_THRESHOLD: float = 0.60

# Column names as produced by compute_rolling_features() + build_training_table()
FEATURE_COLS: list[str] = [
    "temperature_mean_7d",
    "temperature_std_7d",
    "temperature_slope_7d",
    "temperature_mean_30d",
    "temperature_std_30d",
    "temperature_slope_30d",
    "vibration_mean_7d",
    "vibration_std_7d",
    "vibration_slope_7d",
    "vibration_mean_30d",
    "vibration_std_30d",
    "vibration_slope_30d",
    "oil_quality_mean_7d",
    "oil_quality_std_7d",
    "oil_quality_slope_7d",
    "oil_quality_mean_30d",
    "oil_quality_std_30d",
    "oil_quality_slope_30d",
    "partial_discharge_mean_7d",
    "partial_discharge_std_7d",
    "partial_discharge_slope_7d",
    "partial_discharge_mean_30d",
    "partial_discharge_std_30d",
    "partial_discharge_slope_30d",
    "days_since_last_incident",
    "incident_count_90d",
    "criticality_tier",
    "customers_served",
    "asset_age_years",
]

LABEL_COL: str = "failed"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_feature_matrix() -> pd.DataFrame:
    """Load the full training table by re-running the feature pipeline in memory.

    We call build_features directly rather than reading the feature_matrix
    snapshot table (which holds only the latest row per asset) so the model
    trains on all 17,900 daily rows with their rolled features and labels.
    """
    from feature_engineering.build_features import (  # noqa: PLC0415
        _load_tables,
        compute_rolling_features,
        _add_incident_features,
        build_training_table,
    )
    sensor_df, assets_df, incidents_df = _load_tables()
    features_df = compute_rolling_features(sensor_df)
    features_df = _add_incident_features(features_df, incidents_df)
    training_df = build_training_table(features_df, assets_df)

    if training_df.empty:
        raise RuntimeError(
            "Training table is empty. "
            "Run feature_engineering/build_features.py first."
        )
    logger.info("Training table loaded: %d rows.", len(training_df))
    return training_df


# ── Train/test split ──────────────────────────────────────────────────────────

def split_features_labels(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Validate columns and return stratified train/test splits."""
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"feature_matrix is missing columns: {missing}")
    if LABEL_COL not in df.columns:
        raise ValueError(f"feature_matrix is missing the '{LABEL_COL}' column")

    feature_matrix = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median())
    labels = df[LABEL_COL].astype(int)

    return train_test_split(
        feature_matrix,
        labels,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
        stratify=labels,
    )


# ── XGBoost training ──────────────────────────────────────────────────────────

def train_xgboost(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> xgb.XGBClassifier:
    """Train XGBoost with class-imbalance weighting and early stopping.

    scale_pos_weight = (# negative samples) / (# positive samples) compensates
    for the rare failure class so the model does not simply predict healthy for
    all assets.
    """
    scale_pos_weight = float((y_train == 0).sum()) / max((y_train == 1).sum(), 1)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        random_state=RANDOM_SEED,
        early_stopping_rounds=20,
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    return model


# ── Logistic regression baseline ─────────────────────────────────────────────

def train_logistic_baseline(
    X_train: pd.DataFrame, y_train: pd.Series
) -> tuple[LogisticRegression, StandardScaler]:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    lr = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=RANDOM_SEED,
    )
    lr.fit(X_scaled, y_train)
    return lr, scaler


# ── Metric logging ────────────────────────────────────────────────────────────

def _log_metrics(
    name: str,
    y_true: pd.Series,
    y_pred_proba: np.ndarray,
    y_pred_label: np.ndarray,
) -> None:
    auc = roc_auc_score(y_true, y_pred_proba)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred_label, average="binary", zero_division=0
    )
    logger.info(
        "%s — AUC: %.4f | Precision: %.4f | Recall: %.4f | F1: %.4f",
        name, auc, precision, recall, f1,
    )
    if auc < AUC_WARN_THRESHOLD:
        logger.warning(
            "%s AUC %.4f is below %.2f — model may need more training data.",
            name, auc, AUC_WARN_THRESHOLD,
        )


# ── Artifact persistence ──────────────────────────────────────────────────────

def save_artifacts(model: xgb.XGBClassifier) -> None:
    """Persist the XGBoost model, SHAP explainer, and feature metadata to disk."""
    model_dir = Path(MODEL_PATH).parent
    model_dir.mkdir(parents=True, exist_ok=True)

    model.save_model(MODEL_PATH)
    logger.info("XGBoost model saved → %s", MODEL_PATH)

    explainer = shap.TreeExplainer(model)
    joblib.dump(explainer, SHAP_PATH)
    logger.info("SHAP explainer saved → %s", SHAP_PATH)

    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump({"feature_cols": FEATURE_COLS}, fh, indent=2)
    logger.info("Feature metadata saved → %s", META_PATH)


# ── Feature importance logging ────────────────────────────────────────────────

def _log_feature_importances(model: xgb.XGBClassifier) -> None:
    importances = model.feature_importances_
    ranked = sorted(
        zip(FEATURE_COLS, importances), key=lambda t: t[1], reverse=True
    )
    logger.info("Feature importances (XGBoost gain):")
    for feature, score in ranked:
        logger.info("  %-40s %.4f", feature, score)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    np.random.seed(RANDOM_SEED)

    df = load_feature_matrix()
    logger.info("Loaded %d labelled rows from feature_matrix.", len(df))

    X_train, X_test, y_train, y_test = split_features_labels(df)
    logger.info(
        "Train/test split — train: %d, test: %d, failure rate: %.1f%%",
        len(y_train), len(y_test),
        100 * y_train.mean(),
    )

    xgb_model = train_xgboost(X_train, X_test, y_train, y_test)
    xgb_proba = xgb_model.predict_proba(X_test)[:, 1]
    xgb_labels = (xgb_proba >= 0.5).astype(int)
    _log_metrics("XGBoost", y_test, xgb_proba, xgb_labels)
    _log_feature_importances(xgb_model)

    lr_model, scaler = train_logistic_baseline(X_train, y_train)
    lr_proba = lr_model.predict_proba(scaler.transform(X_test))[:, 1]
    lr_labels = lr_model.predict(scaler.transform(X_test))
    _log_metrics("LogisticRegression (baseline)", y_test, lr_proba, lr_labels)

    save_artifacts(xgb_model)
    logger.info("Training complete.")


if __name__ == "__main__":
    main()
