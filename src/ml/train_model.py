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
import psycopg2
import shap
import xgboost as xgb
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
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

FEATURE_COLS: list[str] = [
    "temp_max_24h",
    "temp_mean_24h",
    "temp_delta_per_hour",
    "vibration_max_24h",
    "vibration_mean_24h",
    "vibration_delta_per_hour",
    "pd_max_24h",
    "oil_quality_min_24h",
    "temp_max_72h",
    "vibration_max_72h",
    "temp_zscore_30d",
    "vibration_zscore_30d",
    "days_since_last_incident",
    "incident_count_90d",
    "criticality_tier",
    "customers_served",
    "asset_age_years",
]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_feature_matrix() -> pd.DataFrame:
    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:
        raise RuntimeError(f"Cannot connect to Neon Postgres: {exc}") from exc
    try:
        df = pd.read_sql_query(
            "SELECT * FROM feature_matrix WHERE label IS NOT NULL", conn
        )
    finally:
        conn.close()

    if df.empty:
        raise RuntimeError(
            "feature_matrix has no labelled rows. "
            "Run feature_engineering/build_features.py first."
        )
    return df


# ── Train/test split ──────────────────────────────────────────────────────────

def split_features_labels(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Validate columns and return stratified train/test splits."""
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"feature_matrix is missing columns: {missing}")
    if "label" not in df.columns:
        raise ValueError("feature_matrix is missing the 'label' column")

    feature_matrix = df[FEATURE_COLS].fillna(df[FEATURE_COLS].median())
    labels = df["label"].astype(int)

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
