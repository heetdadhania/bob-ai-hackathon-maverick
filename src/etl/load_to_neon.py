"""
etl/load_to_neon.py

Loads clean DataFrames from transform.py into Neon Postgres via SQLAlchemy.

Upsert strategy: per-table ON CONFLICT clauses via raw SQL executed through the
SQLAlchemy connection.  Chosen over truncate-and-reload because:
  - assets and sensor_readings are referenced by FK constraints; truncating them
    would require disabling constraints or deleting in dependency order.
  - Upsert is idempotent: re-running the full pipeline never duplicates data.
  - Incremental loads (new sensor rows each day) work without touching old rows.

FK-safe load order:  assets → sensor_readings → incidents → weather
  (weather has no FK to assets; it is keyed by region)

Typical usage:
    python -m etl.load_to_neon
"""

import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from etl.extract import extract_all
from etl.transform import clean_and_join

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]
SCHEMA_PATH: Path = Path(__file__).parent / "schema.sql"
UPSERT_BATCH_SIZE: int = 2000

# ── Per-table upsert SQL ──────────────────────────────────────────────────────
# Keyed by table name; each value is the INSERT ... ON CONFLICT statement.
# Column lists must exactly match the current schema.sql definitions.
_UPSERT_SQL: dict[str, str] = {
    "assets": """
        INSERT INTO assets
            (asset_id, asset_type, region, lat, lon,
             install_year, customers_served, criticality_tier)
        VALUES
            (:asset_id, :asset_type, :region, :lat, :lon,
             :install_year, :customers_served, :criticality_tier)
        ON CONFLICT (asset_id) DO UPDATE SET
            asset_type       = EXCLUDED.asset_type,
            region           = EXCLUDED.region,
            lat              = EXCLUDED.lat,
            lon              = EXCLUDED.lon,
            install_year     = EXCLUDED.install_year,
            customers_served = EXCLUDED.customers_served,
            criticality_tier = EXCLUDED.criticality_tier
    """,
    "sensor_readings": """
        INSERT INTO sensor_readings
            (asset_id, date, temperature, vibration,
             oil_quality, partial_discharge, failed)
        VALUES
            (:asset_id, :date, :temperature, :vibration,
             :oil_quality, :partial_discharge, :failed)
        ON CONFLICT (asset_id, date) DO UPDATE SET
            temperature       = EXCLUDED.temperature,
            vibration         = EXCLUDED.vibration,
            oil_quality       = EXCLUDED.oil_quality,
            partial_discharge = EXCLUDED.partial_discharge,
            failed            = EXCLUDED.failed
    """,
    "incidents": """
        INSERT INTO incidents
            (incident_id, asset_id, date, cause,
             duration_hours, customers_affected)
        VALUES
            (:incident_id, :asset_id, :date, :cause,
             :duration_hours, :customers_affected)
        ON CONFLICT (incident_id) DO NOTHING
    """,
    "weather": """
        INSERT INTO weather
            (region, date, temperature_max, precipitation_sum, windspeed_max)
        VALUES
            (:region, :date, :temperature_max, :precipitation_sum, :windspeed_max)
        ON CONFLICT (region, date) DO UPDATE SET
            temperature_max   = EXCLUDED.temperature_max,
            precipitation_sum = EXCLUDED.precipitation_sum,
            windspeed_max     = EXCLUDED.windspeed_max
    """,
}

# Columns to select from each DataFrame before loading (avoids passing extra
# join columns to tables that don't have those fields)
_TABLE_COLUMNS: dict[str, list[str]] = {
    "assets": [
        "asset_id", "asset_type", "region", "lat", "lon",
        "install_year", "customers_served", "criticality_tier",
    ],
    "sensor_readings": [
        "asset_id", "date", "temperature", "vibration",
        "oil_quality", "partial_discharge", "failed",
    ],
    "incidents": [
        "incident_id", "asset_id", "date", "cause",
        "duration_hours", "customers_affected",
    ],
    "weather": [
        "region", "date", "temperature_max", "precipitation_sum", "windspeed_max",
    ],
}


# ── Engine factory ────────────────────────────────────────────────────────────

def build_engine() -> Engine:
    try:
        engine = create_engine(DB_URL, pool_pre_ping=True)
        return engine
    except Exception as exc:
        raise RuntimeError(f"Cannot create SQLAlchemy engine: {exc}") from exc


# ── Schema bootstrap ──────────────────────────────────────────────────────────

def ensure_schema(engine: Engine) -> None:
    """Run schema.sql if it has not been applied yet.

    Uses CREATE TABLE IF NOT EXISTS semantics in schema.sql so this is safe
    to call on every pipeline run — it is a no-op when tables already exist.
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"schema.sql not found at {SCHEMA_PATH.resolve()}. "
            "Cannot initialise database."
        )
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        with engine.begin() as conn:
            conn.execute(text(schema_sql))
        logger.info("Schema verified / applied from %s", SCHEMA_PATH.name)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Failed to apply schema: {exc}") from exc


# ── Generic loader ────────────────────────────────────────────────────────────

def load_dataframe(df: pd.DataFrame, table_name: str, engine: Engine) -> None:
    """Upsert all rows of *df* into *table_name* using a batched INSERT … ON CONFLICT.

    Only the columns listed in _TABLE_COLUMNS[table_name] are written; extra
    columns present in the DataFrame (e.g. from the enrichment join) are ignored.
    The entire load for this table is wrapped in a single transaction; any error
    triggers an automatic rollback via SQLAlchemy's context manager.
    """
    if table_name not in _UPSERT_SQL:
        raise ValueError(
            f"Unknown table '{table_name}'. "
            f"Expected one of: {sorted(_UPSERT_SQL.keys())}"
        )

    required_cols = set(_TABLE_COLUMNS[table_name])
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame for '{table_name}' is missing columns: {sorted(missing)}"
        )

    subset = df[_TABLE_COLUMNS[table_name]].copy()
    records = subset.to_dict("records")
    total = len(records)

    try:
        with engine.begin() as conn:
            for batch_start in range(0, total, UPSERT_BATCH_SIZE):
                batch = records[batch_start: batch_start + UPSERT_BATCH_SIZE]
                conn.execute(text(_UPSERT_SQL[table_name]), batch)
        logger.info("Loaded '%s': %d rows upserted", table_name, total)
    except SQLAlchemyError as exc:
        raise RuntimeError(
            f"Failed to load table '{table_name}' (rolled back): {exc}"
        ) from exc


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    engine = build_engine()
    ensure_schema(engine)

    logger.info("Extracting from CSV files...")
    assets_df, sensor_df, incidents_df, weather_df = extract_all()

    logger.info("Transforming and joining...")
    enriched_df, clean_incidents_df = clean_and_join(
        assets_df, sensor_df, incidents_df, weather_df
    )

    # Load in FK-safe order: assets first, then tables that reference it
    load_dataframe(assets_df, "assets", engine)
    load_dataframe(enriched_df, "sensor_readings", engine)
    load_dataframe(clean_incidents_df, "incidents", engine)
    load_dataframe(weather_df, "weather", engine)

    logger.info("ETL pipeline complete.")


if __name__ == "__main__":
    main()
