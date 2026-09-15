"""
data_generation/generate_fake_data.py

Generates synthetic grid assets, daily sensor readings, and incident history.
Writes each dataset to a CSV file (OUTPUT_DIR from .env) and also upserts
all rows into the Neon Postgres tables defined in etl/schema.sql.

Run:
    python data_generation/generate_fake_data.py
"""

import logging
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "data_generation/output"))

# ── Generation parameters ─────────────────────────────────────────────────────
N_ASSETS: int = 100
FAILURE_RATE: float = 0.15          # ~15 % of assets will_fail
SENSOR_DAYS: int = 180
N_INCIDENTS: int = 25
DEGRADATION_WINDOW_DAYS: int = 30   # ramp starts this many days before failure

ASSET_TYPES: list[str] = ["transformer", "substation", "breaker"]
REGIONS: list[str] = ["North", "South", "East", "West", "Central"]
INCIDENT_CAUSES: list[str] = [
    "thermal_overload", "insulation_failure",
    "mechanical_fault", "weather_damage", "age_degradation",
]

LAT_RANGE: tuple[float, float] = (30.0, 48.0)
LON_RANGE: tuple[float, float] = (-120.0, -75.0)

RANDOM_SEED: int = 42


# ── Public generation functions ───────────────────────────────────────────────

def generate_assets(n_assets: int) -> pd.DataFrame:
    """Return a DataFrame of n_assets synthetic grid assets."""
    if n_assets < 1:
        raise ValueError(f"n_assets must be >= 1, got {n_assets}")

    rng = np.random.default_rng(RANDOM_SEED)

    asset_ids = [f"ASSET-{uuid.uuid4().hex[:8].upper()}" for _ in range(n_assets)]
    return pd.DataFrame({
        "asset_id": asset_ids,
        "asset_type": rng.choice(ASSET_TYPES, size=n_assets),
        "region": rng.choice(REGIONS, size=n_assets),
        "lat": np.round(rng.uniform(*LAT_RANGE, size=n_assets), 5),
        "lon": np.round(rng.uniform(*LON_RANGE, size=n_assets), 5),
        "install_year": rng.integers(1975, 2016, size=n_assets),
        "customers_served": rng.integers(100, 80_001, size=n_assets),
        "criticality_tier": rng.integers(1, 4, size=n_assets),
    })


def generate_sensor_series(
    asset_id: str, will_fail: bool, days: int
) -> pd.DataFrame:
    """Return daily sensor readings for one asset over *days* days.

    Baseline values are drawn from stable normal distributions.  When
    will_fail=True a linear degradation ramp is applied in the final
    DEGRADATION_WINDOW_DAYS: temperature and vibration rise, partial
    discharge spikes, and oil quality falls — giving XGBoost a learnable
    failure signature.  The failed flag is set to 1 only on the final day
    of a failing asset (ground-truth label for supervised training).
    """
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")

    rng = np.random.default_rng(RANDOM_SEED ^ hash(asset_id) & 0xFFFFFFFF)

    today = date.today()
    dates = [today - timedelta(days=(days - 1 - i)) for i in range(days)]

    temperature = rng.normal(65.0, 3.0, size=days)
    vibration = rng.normal(1.5, 0.2, size=days)
    partial_discharge = rng.normal(50.0, 10.0, size=days)
    oil_quality = rng.normal(80.0, 5.0, size=days)
    failed = np.zeros(days, dtype=int)

    if will_fail:
        ramp_start = days - DEGRADATION_WINDOW_DAYS
        for i in range(max(ramp_start, 0), days):
            progress = (i - ramp_start) / DEGRADATION_WINDOW_DAYS
            temperature[i] += progress * rng.normal(25.0, 3.0)
            vibration[i] += progress * rng.normal(3.5, 0.5)
            partial_discharge[i] += progress * rng.normal(200.0, 30.0)
            oil_quality[i] -= progress * rng.normal(25.0, 4.0)
        failed[-1] = 1

    return pd.DataFrame({
        "asset_id": asset_id,
        "date": dates,
        "temperature": np.round(np.clip(temperature, 20.0, 140.0), 2),
        "vibration": np.round(np.clip(vibration, 0.1, 15.0), 3),
        "oil_quality": np.round(np.clip(oil_quality, 0.0, 100.0), 1),
        "partial_discharge": np.round(np.clip(partial_discharge, 0.0, 1000.0), 1),
        "failed": failed,
    })


def generate_incidents(
    assets_df: pd.DataFrame, n_incidents: int
) -> pd.DataFrame:
    """Return n_incidents synthetic outage events drawn from assets_df."""
    required_cols = {"asset_id"}
    if missing := required_cols - set(assets_df.columns):
        raise ValueError(f"assets_df is missing columns: {missing}")
    if n_incidents < 1:
        raise ValueError(f"n_incidents must be >= 1, got {n_incidents}")

    rng = np.random.default_rng(RANDOM_SEED)
    today = date.today()

    sampled_asset_ids = rng.choice(
        assets_df["asset_id"].to_numpy(), size=n_incidents, replace=True
    )
    incident_dates = [
        today - timedelta(days=int(rng.integers(1, 181))) for _ in range(n_incidents)
    ]
    causes = rng.choice(INCIDENT_CAUSES, size=n_incidents)
    duration_hours = np.round(rng.uniform(0.5, 72.0, size=n_incidents), 2)
    customers_affected = rng.integers(50, 10_001, size=n_incidents)

    return pd.DataFrame({
        "incident_id": [f"INC-{uuid.uuid4().hex[:8].upper()}" for _ in range(n_incidents)],
        "asset_id": sampled_asset_ids,
        "date": incident_dates,
        "cause": causes,
        "duration_hours": duration_hours,
        "customers_affected": customers_affected,
    })


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csvs(
    assets_df: pd.DataFrame,
    sensor_df: pd.DataFrame,
    incidents_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_path = output_dir / "assets.csv"
    sensor_path = output_dir / "sensor_readings.csv"
    incidents_path = output_dir / "incidents.csv"

    assets_df.to_csv(assets_path, index=False)
    sensor_df.to_csv(sensor_path, index=False)
    incidents_df.to_csv(incidents_path, index=False)

    logger.info("CSV files written to %s", output_dir.resolve())


# ── DB writer ─────────────────────────────────────────────────────────────────

def _upsert_assets(cur: psycopg2.extensions.cursor, assets_df: pd.DataFrame) -> None:
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO assets
            (asset_id, asset_type, region, lat, lon,
             install_year, customers_served, criticality_tier)
        VALUES
            (%(asset_id)s, %(asset_type)s, %(region)s, %(lat)s, %(lon)s,
             %(install_year)s, %(customers_served)s, %(criticality_tier)s)
        ON CONFLICT (asset_id) DO NOTHING
        """,
        assets_df.to_dict("records"),
        page_size=500,
    )
    logger.info("Upserted %d assets", len(assets_df))


def _upsert_sensor_readings(
    cur: psycopg2.extensions.cursor, sensor_df: pd.DataFrame
) -> None:
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO sensor_readings
            (asset_id, date, temperature, vibration,
             oil_quality, partial_discharge, failed)
        VALUES
            (%(asset_id)s, %(date)s, %(temperature)s, %(vibration)s,
             %(oil_quality)s, %(partial_discharge)s, %(failed)s)
        ON CONFLICT (asset_id, date) DO NOTHING
        """,
        sensor_df.to_dict("records"),
        page_size=1000,
    )
    logger.info("Upserted %d sensor rows", len(sensor_df))


def _upsert_incidents(
    cur: psycopg2.extensions.cursor, incidents_df: pd.DataFrame
) -> None:
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO incidents
            (incident_id, asset_id, date, cause,
             duration_hours, customers_affected)
        VALUES
            (%(incident_id)s, %(asset_id)s, %(date)s, %(cause)s,
             %(duration_hours)s, %(customers_affected)s)
        ON CONFLICT (incident_id) DO NOTHING
        """,
        incidents_df.to_dict("records"),
        page_size=500,
    )
    logger.info("Upserted %d incidents", len(incidents_df))


def write_to_db(
    assets_df: pd.DataFrame,
    sensor_df: pd.DataFrame,
    incidents_df: pd.DataFrame,
) -> None:
    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:
        raise RuntimeError(f"Cannot connect to Neon Postgres: {exc}") from exc

    try:
        with conn:
            with conn.cursor() as cur:
                _upsert_assets(cur, assets_df)
                _upsert_sensor_readings(cur, sensor_df)
                _upsert_incidents(cur, incidents_df)
        logger.info("All data written to Neon Postgres.")
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    np.random.seed(RANDOM_SEED)

    assets_df = generate_assets(N_ASSETS)

    failing_asset_ids = set(
        assets_df["asset_id"].sample(
            frac=FAILURE_RATE, random_state=RANDOM_SEED
        )
    )
    logger.info(
        "Generating sensor data: %d assets (%d will fail)",
        N_ASSETS,
        len(failing_asset_ids),
    )

    sensor_frames: list[pd.DataFrame] = [
        generate_sensor_series(
            asset_id=row["asset_id"],
            will_fail=row["asset_id"] in failing_asset_ids,
            days=SENSOR_DAYS,
        )
        for _, row in assets_df.iterrows()
    ]
    sensor_df = pd.concat(sensor_frames, ignore_index=True)

    incidents_df = generate_incidents(assets_df, N_INCIDENTS)

    write_csvs(assets_df, sensor_df, incidents_df, OUTPUT_DIR)
    write_to_db(assets_df, sensor_df, incidents_df)

    logger.info(
        "Done — %d assets, %d sensor rows, %d incidents.",
        len(assets_df),
        len(sensor_df),
        len(incidents_df),
    )


if __name__ == "__main__":
    main()
