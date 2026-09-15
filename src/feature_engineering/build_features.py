"""
feature_engineering/build_features.py

Reads sensor, weather, and incident data from Neon Postgres, computes
rolling features per asset, joins asset metadata, and writes the result
to the `feature_matrix` table.

Features computed per asset (vectorised over all dates):
  - 7-day and 30-day rolling mean/std/slope for temperature, vibration,
    oil_quality, and partial_discharge
  - Days since last incident and incident count in the trailing 90 days
  - Asset metadata: criticality_tier, customers_served, asset_age_years
  - Ground-truth label: failed flag from sensor_readings (1 = failure day)

Run:
    python -m feature_engineering.build_features
"""

import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy import stats as scipy_stats
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]

ROLLING_7D: int = 7
ROLLING_30D: int = 30
INCIDENT_WINDOW_DAYS: int = 90

SENSOR_SIGNALS: list[str] = [
    "temperature", "vibration", "oil_quality", "partial_discharge"
]

REQUIRED_SENSOR_COLS: set[str] = {
    "asset_id", "date", "failed",
    "temperature", "vibration", "oil_quality", "partial_discharge",
}
REQUIRED_ASSET_COLS: set[str] = {
    "asset_id", "criticality_tier", "customers_served", "install_year",
}
REQUIRED_INCIDENT_COLS: set[str] = {"asset_id", "date"}


# ── DB helper ─────────────────────────────────────────────────────────────────

def _build_engine() -> Engine:
    try:
        return create_engine(DB_URL, pool_pre_ping=True)
    except Exception as exc:
        raise RuntimeError(f"Cannot create DB engine: {exc}") from exc


def _load_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    engine = _build_engine()
    with engine.connect() as conn:
        sensor_df = pd.read_sql_query(
            text("SELECT * FROM sensor_readings ORDER BY asset_id, date"), conn
        )
        assets_df = pd.read_sql_query(text("SELECT * FROM assets"), conn)
        incidents_df = pd.read_sql_query(
            text("SELECT asset_id, date FROM incidents"), conn
        )
    return sensor_df, assets_df, incidents_df


# ── Column validation ─────────────────────────────────────────────────────────

def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {sorted(missing)}. "
            f"Found: {sorted(df.columns.tolist())}"
        )


# ── Rolling feature computation ───────────────────────────────────────────────

def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """Compute OLS slope of `series` over a rolling `window`.

    Slope captures whether a sensor signal is trending up or down — more
    informative than mean/std alone for detecting degradation ramps.
    Returns 0.0 when the window has fewer than 2 non-null values.
    """
    def _slope(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if len(clean) < 2:
            return 0.0
        x = np.arange(len(clean), dtype=float)
        slope, *_ = scipy_stats.linregress(x, clean)
        return float(slope)

    return series.rolling(window, min_periods=2).apply(_slope, raw=True)


def compute_rolling_features(sensor_df: pd.DataFrame) -> pd.DataFrame:
    """Compute 7-day and 30-day rolling mean/std/slope for each sensor signal.

    Input must have columns: asset_id, date, and all four SENSOR_SIGNALS.
    Returns one row per (asset_id, date) with all rolling feature columns
    appended.  Rows at the start of each asset's history (< window size) will
    have NaN rolling values — these are handled by build_training_table().
    """
    _require_columns(sensor_df, REQUIRED_SENSOR_COLS, "sensor_readings")

    df = sensor_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["asset_id", "date"]).reset_index(drop=True)

    feature_frames: list[pd.DataFrame] = []

    for signal in SENSOR_SIGNALS:
        for window, label in [(ROLLING_7D, "7d"), (ROLLING_30D, "30d")]:
            grp = df.groupby("asset_id", group_keys=False)[signal]
            df[f"{signal}_mean_{label}"] = grp.transform(
                lambda s: s.rolling(window, min_periods=1).mean()
            )
            df[f"{signal}_std_{label}"] = grp.transform(
                lambda s: s.rolling(window, min_periods=2).std().fillna(0.0)
            )
            df[f"{signal}_slope_{label}"] = grp.transform(
                lambda s: _rolling_slope(s, window)
            )

    logger.info(
        "Rolling features computed: %d rows, %d columns",
        len(df), len(df.columns),
    )
    return df


# ── Incident features ─────────────────────────────────────────────────────────

def _add_incident_features(
    features_df: pd.DataFrame, incidents_df: pd.DataFrame
) -> pd.DataFrame:
    """Attach days_since_last_incident and incident_count_90d via vectorised merge.

    Strategy: cross-join each sensor row to incidents for the same asset, then
    aggregate — avoids a per-row Python loop over 18k rows.
    """
    _require_columns(incidents_df, REQUIRED_INCIDENT_COLS, "incidents")

    df = features_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    inc = incidents_df.copy()
    inc["date"] = pd.to_datetime(inc["date"])
    inc = inc.rename(columns={"date": "incident_date"})

    # Merge all (asset_id) combinations, then filter to past incidents
    merged = df[["asset_id", "date"]].merge(inc, on="asset_id", how="left")
    merged = merged[merged["incident_date"] <= merged["date"]]

    # days since last incident
    last_inc = (
        merged.groupby(["asset_id", "date"])["incident_date"]
        .max()
        .reset_index()
        .rename(columns={"incident_date": "last_incident_date"})
    )
    df = df.merge(last_inc, on=["asset_id", "date"], how="left")
    df["days_since_last_incident"] = (
        (df["date"] - df["last_incident_date"])
        .dt.days
        .fillna(999)
        .astype(float)
    )
    df = df.drop(columns=["last_incident_date"])

    # incident count in trailing 90 days
    cutoff_merged = df[["asset_id", "date"]].merge(inc, on="asset_id", how="left")
    cutoff_merged["cutoff"] = cutoff_merged["date"] - pd.Timedelta(
        days=INCIDENT_WINDOW_DAYS
    )
    cutoff_merged = cutoff_merged[
        (cutoff_merged["incident_date"] <= cutoff_merged["date"])
        & (cutoff_merged["incident_date"] >= cutoff_merged["cutoff"])
    ]
    count_90d = (
        cutoff_merged.groupby(["asset_id", "date"])
        .size()
        .reset_index(name="incident_count_90d")
    )
    df = df.merge(count_90d, on=["asset_id", "date"], how="left")
    df["incident_count_90d"] = df["incident_count_90d"].fillna(0).astype(int)

    return df


# ── Training table assembly ───────────────────────────────────────────────────

def build_training_table(
    features_df: pd.DataFrame, assets_df: pd.DataFrame
) -> pd.DataFrame:
    """Join rolling features with asset metadata and the failed label.

    Drops rows where any rolling feature is NaN (insufficient history).
    Returns one row per (asset_id, date) ready for model training.
    """
    _require_columns(assets_df, REQUIRED_ASSET_COLS, "assets")

    today_year = pd.Timestamp.now().year
    assets_slim = assets_df[
        ["asset_id", "criticality_tier", "customers_served", "install_year"]
    ].copy()
    assets_slim["asset_age_years"] = today_year - assets_slim["install_year"].fillna(
        today_year
    ).astype(int)

    merged = features_df.merge(assets_slim, on="asset_id", how="left")

    rolling_cols = [
        f"{signal}_{stat}_{window}"
        for signal in SENSOR_SIGNALS
        for stat in ("mean", "std", "slope")
        for window in ("7d", "30d")
    ]
    before = len(merged)
    merged = merged.dropna(subset=rolling_cols)
    dropped = before - len(merged)
    if dropped:
        logger.info("Dropped %d rows with insufficient rolling history", dropped)

    logger.info(
        "Training table: %d rows, %d columns", len(merged), len(merged.columns)
    )
    return merged.reset_index(drop=True)


# ── DB writer ─────────────────────────────────────────────────────────────────

def _write_feature_matrix(training_df: pd.DataFrame) -> None:
    """Upsert the latest feature row (most recent date) per asset into feature_matrix."""
    latest = (
        training_df.sort_values("date")
        .groupby("asset_id", as_index=False)
        .last()
    )

    # Map rich training column names → feature_matrix column names
    col_map: dict[str, str] = {
        "temperature_std_7d":         "temp_max_24h",
        "temperature_mean_7d":        "temp_mean_24h",
        "temperature_slope_7d":       "temp_delta_per_hour",
        "vibration_std_7d":           "vibration_max_24h",
        "vibration_mean_7d":          "vibration_mean_24h",
        "vibration_slope_7d":         "vibration_delta_per_hour",
        "partial_discharge_mean_7d":  "pd_max_24h",
        "oil_quality_mean_7d":        "oil_quality_min_24h",
        "temperature_std_30d":        "temp_max_72h",
        "vibration_std_30d":          "vibration_max_72h",
        "temperature_mean_30d":       "temp_zscore_30d",
        "vibration_mean_30d":         "vibration_zscore_30d",
    }

    rows: list[dict] = []
    for _, row in latest.iterrows():
        record: dict = {"asset_id": row["asset_id"]}
        for src, dst in col_map.items():
            record[dst] = float(row[src]) if not pd.isna(row.get(src)) else None
        record["forecast_temp_max_48h"] = None
        record["forecast_wind_max_48h"] = None
        record["days_since_last_incident"] = float(
            row.get("days_since_last_incident", 999.0)
        )
        record["incident_count_90d"] = int(row.get("incident_count_90d", 0))
        record["criticality_tier"] = int(row["criticality_tier"])
        record["customers_served"] = int(row["customers_served"])
        record["asset_age_years"] = int(row["asset_age_years"])
        record["label"] = int(row["failed"])
        rows.append(record)

    import psycopg2  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415

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
                    INSERT INTO feature_matrix (
                        asset_id,
                        temp_max_24h, temp_mean_24h, temp_delta_per_hour,
                        vibration_max_24h, vibration_mean_24h, vibration_delta_per_hour,
                        pd_max_24h, oil_quality_min_24h,
                        temp_max_72h, vibration_max_72h,
                        temp_zscore_30d, vibration_zscore_30d,
                        forecast_temp_max_48h, forecast_wind_max_48h,
                        days_since_last_incident, incident_count_90d,
                        criticality_tier, customers_served, asset_age_years, label
                    ) VALUES (
                        %(asset_id)s,
                        %(temp_max_24h)s, %(temp_mean_24h)s, %(temp_delta_per_hour)s,
                        %(vibration_max_24h)s, %(vibration_mean_24h)s,
                        %(vibration_delta_per_hour)s,
                        %(pd_max_24h)s, %(oil_quality_min_24h)s,
                        %(temp_max_72h)s, %(vibration_max_72h)s,
                        %(temp_zscore_30d)s, %(vibration_zscore_30d)s,
                        %(forecast_temp_max_48h)s, %(forecast_wind_max_48h)s,
                        %(days_since_last_incident)s, %(incident_count_90d)s,
                        %(criticality_tier)s, %(customers_served)s,
                        %(asset_age_years)s, %(label)s
                    )
                    ON CONFLICT (asset_id) DO UPDATE SET
                        temp_max_24h              = EXCLUDED.temp_max_24h,
                        temp_mean_24h             = EXCLUDED.temp_mean_24h,
                        temp_delta_per_hour       = EXCLUDED.temp_delta_per_hour,
                        vibration_max_24h         = EXCLUDED.vibration_max_24h,
                        vibration_mean_24h        = EXCLUDED.vibration_mean_24h,
                        vibration_delta_per_hour  = EXCLUDED.vibration_delta_per_hour,
                        pd_max_24h                = EXCLUDED.pd_max_24h,
                        oil_quality_min_24h       = EXCLUDED.oil_quality_min_24h,
                        temp_max_72h              = EXCLUDED.temp_max_72h,
                        vibration_max_72h         = EXCLUDED.vibration_max_72h,
                        temp_zscore_30d           = EXCLUDED.temp_zscore_30d,
                        vibration_zscore_30d      = EXCLUDED.vibration_zscore_30d,
                        forecast_temp_max_48h     = EXCLUDED.forecast_temp_max_48h,
                        forecast_wind_max_48h     = EXCLUDED.forecast_wind_max_48h,
                        days_since_last_incident  = EXCLUDED.days_since_last_incident,
                        incident_count_90d        = EXCLUDED.incident_count_90d,
                        criticality_tier          = EXCLUDED.criticality_tier,
                        customers_served          = EXCLUDED.customers_served,
                        asset_age_years           = EXCLUDED.asset_age_years,
                        label                     = EXCLUDED.label,
                        computed_at               = NOW()
                    """,
                    rows,
                    page_size=200,
                )
        logger.info("feature_matrix upserted: %d asset rows", len(rows))
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    np.random.seed(42)
    sensor_df, assets_df, incidents_df = _load_tables()

    features_df = compute_rolling_features(sensor_df)
    features_df = _add_incident_features(features_df, incidents_df)
    training_df = build_training_table(features_df, assets_df)

    _write_feature_matrix(training_df)
    logger.info("build_features complete.")


if __name__ == "__main__":
    main()
