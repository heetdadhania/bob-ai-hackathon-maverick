"""
etl/transform.py

Cleans the four raw DataFrames from extract.py and joins them into a single
enriched sensor DataFrame ready for feature engineering.

Join graph:
    sensor_readings
        → assets       on asset_id           (attaches region, metadata)
        → weather      on region + date       (attaches daily weather context)

Missing-value strategy (documented per column group):
    asset_id          — rows with null asset_id are dropped; no valid join is possible
    sensor signals    — forward-filled within each asset up to MAX_FFILL_DAYS consecutive
                        gaps (covers short outages); rows still null after fill are dropped
    weather columns   — left-joined; nulls filled with regional daily median so every
                        sensor row retains a weather value; residual nulls dropped
    incidents         — cleaned independently; returned separately for feature engineering

Typical usage:
    from etl.extract import extract_all
    from etl.transform import clean_and_join
    enriched_df, clean_incidents_df = clean_and_join(*extract_all())
"""

import logging

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Physical bounds for sensor clipping ───────────────────────────────────────
SENSOR_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature":       (0.0,   160.0),
    "vibration":         (0.0,    20.0),
    "partial_discharge": (0.0,  2000.0),
    "oil_quality":       (0.0,   100.0),
}

# ── Physical bounds for weather clipping ──────────────────────────────────────
WEATHER_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_max":   (-60.0,  60.0),
    "windspeed_max":       (0.0, 300.0),
    "precipitation_sum":   (0.0, 500.0),
}

# Max consecutive days to forward-fill per asset before treating as data loss
MAX_FFILL_DAYS: int = 3


# ── Column validation helper ──────────────────────────────────────────────────

def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{label} is missing required columns: {sorted(missing)}. "
            f"Found: {sorted(df.columns.tolist())}"
        )


# ── Per-table cleaners ────────────────────────────────────────────────────────

def _clean_assets(assets_df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        assets_df,
        {"asset_id", "asset_type", "region", "lat", "lon",
         "install_year", "customers_served", "criticality_tier"},
        "assets",
    )
    df = assets_df.copy()
    before = len(df)
    df = df.dropna(subset=["asset_id"])
    df = df.drop_duplicates(subset=["asset_id"])
    df["customers_served"] = df["customers_served"].clip(lower=0)
    df["criticality_tier"] = df["criticality_tier"].clip(1, 3)
    logger.info("assets: %d → %d rows after clean", before, len(df))
    return df.reset_index(drop=True)


def _clean_sensor_readings(sensor_df: pd.DataFrame) -> pd.DataFrame:
    """Clean sensor readings.

    Steps:
      1. Drop rows with null asset_id (unjoignable).
      2. Standardize date column to Python date objects.
      3. Deduplicate on (asset_id, date) — keep first.
      4. Clip sensor values to physical bounds.
      5. Forward-fill short gaps (≤ MAX_FFILL_DAYS) per asset, then drop remaining nulls.
    """
    _require_columns(
        sensor_df,
        {"asset_id", "date", "temperature", "vibration",
         "oil_quality", "partial_discharge", "failed"},
        "sensor_readings",
    )
    df = sensor_df.copy()
    before = len(df)

    df = df.dropna(subset=["asset_id"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates(subset=["asset_id", "date"])

    for col, (lo, hi) in SENSOR_BOUNDS.items():
        df[col] = df[col].clip(lo, hi)

    sensor_cols = list(SENSOR_BOUNDS.keys())
    df = df.sort_values(["asset_id", "date"]).reset_index(drop=True)
    df[sensor_cols] = (
        df.groupby("asset_id", group_keys=False)[sensor_cols]
        .apply(lambda g: g.ffill(limit=MAX_FFILL_DAYS))
    )
    df = df.dropna(subset=sensor_cols)

    logger.info("sensor_readings: %d → %d rows after clean", before, len(df))
    return df.reset_index(drop=True)


def _clean_weather(weather_df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        weather_df,
        {"region", "date", "temperature_max", "precipitation_sum", "windspeed_max"},
        "weather",
    )
    df = weather_df.copy()
    before = len(df)

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates(subset=["region", "date"])

    for col, (lo, hi) in WEATHER_BOUNDS.items():
        df[col] = df[col].clip(lo, hi)

    logger.info("weather: %d → %d rows after clean", before, len(df))
    return df.reset_index(drop=True)


def _clean_incidents(incidents_df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        incidents_df,
        {"incident_id", "asset_id", "date", "cause",
         "duration_hours", "customers_affected"},
        "incidents",
    )
    df = incidents_df.copy()
    before = len(df)

    df = df.dropna(subset=["asset_id"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates(subset=["incident_id"])
    df["duration_hours"] = df["duration_hours"].clip(lower=0)
    df["customers_affected"] = df["customers_affected"].clip(lower=0)

    logger.info("incidents: %d → %d rows after clean", before, len(df))
    return df.reset_index(drop=True)


# ── Join logic ────────────────────────────────────────────────────────────────

def _join_sensor_to_assets(
    sensor_df: pd.DataFrame, assets_df: pd.DataFrame
) -> pd.DataFrame:
    """Left-join sensor readings to assets on asset_id.

    Rows whose asset_id has no matching asset record are dropped — they cannot
    be enriched and would break downstream feature engineering.
    """
    asset_cols = ["asset_id", "region", "lat", "lon",
                  "install_year", "customers_served", "criticality_tier", "asset_type"]
    enriched = sensor_df.merge(
        assets_df[asset_cols],
        on="asset_id",
        how="left",
    )
    before = len(enriched)
    enriched = enriched.dropna(subset=["region"])
    dropped = before - len(enriched)
    if dropped:
        logger.warning(
            "Dropped %d sensor rows with no matching asset record", dropped
        )
    return enriched


def _join_weather(
    enriched_df: pd.DataFrame, weather_df: pd.DataFrame
) -> pd.DataFrame:
    """Left-join weather to the enriched sensor DataFrame on (region, date).

    After the join, any weather nulls are filled with the regional daily median
    for that column.  Rows still null after median-fill (e.g. a region with no
    weather data at all) are dropped.
    """
    joined = enriched_df.merge(
        weather_df,
        on=["region", "date"],
        how="left",
    )

    weather_cols = list(WEATHER_BOUNDS.keys())
    for col in weather_cols:
        median_col = f"{col}_median"
        regional_medians = (
            weather_df.groupby("region")[col]
            .median()
            .reset_index()
            .rename(columns={col: median_col})
        )
        joined = joined.merge(regional_medians, on="region", how="left")
        joined[col] = joined[col].fillna(joined[median_col])
        joined = joined.drop(columns=[median_col])

    before = len(joined)
    joined = joined.dropna(subset=weather_cols)
    dropped = before - len(joined)
    if dropped:
        logger.warning(
            "Dropped %d rows with no weather data after median fill", dropped
        )
    return joined


# ── Public entry point ────────────────────────────────────────────────────────

def clean_and_join(
    assets_df: pd.DataFrame,
    sensor_df: pd.DataFrame,
    incidents_df: pd.DataFrame,
    weather_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean all four DataFrames, join sensor → assets → weather, and return:

        (enriched_df, clean_incidents_df)

    enriched_df has one row per (asset_id, date) with sensor readings,
    asset metadata, and daily weather context attached.
    clean_incidents_df is cleaned independently for use in feature engineering.
    """
    clean_assets = _clean_assets(assets_df)
    clean_sensor = _clean_sensor_readings(sensor_df)
    clean_weather = _clean_weather(weather_df)
    clean_incidents = _clean_incidents(incidents_df)

    enriched = _join_sensor_to_assets(clean_sensor, clean_assets)
    enriched = _join_weather(enriched, clean_weather)

    logger.info(
        "Transform complete — enriched_df: %d rows, %d columns",
        len(enriched), len(enriched.columns),
    )
    return enriched, clean_incidents


# ── Script entry point ────────────────────────────────────────────────────────

def main() -> None:
    from etl.extract import extract_all  # imported here to keep modules decoupled

    assets_df, sensor_df, incidents_df, weather_df = extract_all()
    enriched_df, clean_incidents_df = clean_and_join(
        assets_df, sensor_df, incidents_df, weather_df
    )
    logger.info(
        "Enriched columns: %s", enriched_df.columns.tolist()
    )
    logger.info(
        "Incidents columns: %s", clean_incidents_df.columns.tolist()
    )


if __name__ == "__main__":
    main()
