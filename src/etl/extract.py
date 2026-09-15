"""
etl/extract.py

Reads the CSV files produced by data_generation/ into pandas DataFrames.
Validates that each file exists and contains the expected columns before
returning the data.

Typical usage:
    from etl.extract import extract_all
    assets_df, sensor_df, incidents_df, weather_df = extract_all()
"""

import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "data_generation/output"))

# ── Expected columns per file ─────────────────────────────────────────────────
ASSETS_COLUMNS: frozenset[str] = frozenset({
    "asset_id", "asset_type", "region", "lat", "lon",
    "install_year", "customers_served", "criticality_tier",
})
SENSOR_COLUMNS: frozenset[str] = frozenset({
    "asset_id", "date", "temperature", "vibration",
    "oil_quality", "partial_discharge", "failed",
})
INCIDENTS_COLUMNS: frozenset[str] = frozenset({
    "incident_id", "asset_id", "date", "cause",
    "duration_hours", "customers_affected",
})
WEATHER_COLUMNS: frozenset[str] = frozenset({
    "region", "date", "temperature_max", "precipitation_sum", "windspeed_max",
})


# ── Single-file loader ────────────────────────────────────────────────────────

def _load_csv(file_path: Path, expected_columns: frozenset[str]) -> pd.DataFrame:
    """Load a CSV file and validate that all expected columns are present.

    Raises FileNotFoundError if the file does not exist and ValueError if any
    expected columns are missing — both with a clear, actionable message.
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {file_path.resolve()}. "
            "Run data_generation/ scripts first."
        )

    try:
        df = pd.read_csv(file_path)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse CSV file {file_path.resolve()}: {exc}"
        ) from exc

    missing_cols = expected_columns - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"File {file_path.name} is missing expected columns: {sorted(missing_cols)}. "
            f"Found: {sorted(df.columns.tolist())}"
        )

    logger.info("Loaded %s: %d rows, %d columns", file_path.name, len(df), len(df.columns))
    return df


# ── Per-table extractors ──────────────────────────────────────────────────────

def extract_assets(output_dir: Path) -> pd.DataFrame:
    df = _load_csv(output_dir / "assets.csv", ASSETS_COLUMNS)
    df["install_year"] = pd.to_numeric(df["install_year"], errors="coerce")
    df["customers_served"] = pd.to_numeric(df["customers_served"], errors="coerce")
    df["criticality_tier"] = pd.to_numeric(df["criticality_tier"], errors="coerce")
    return df


def extract_sensor_readings(output_dir: Path) -> pd.DataFrame:
    df = _load_csv(output_dir / "sensor_readings.csv", SENSOR_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def extract_incidents(output_dir: Path) -> pd.DataFrame:
    df = _load_csv(output_dir / "incidents.csv", INCIDENTS_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce")
    df["customers_affected"] = pd.to_numeric(df["customers_affected"], errors="coerce")
    return df


def extract_weather(output_dir: Path) -> pd.DataFrame:
    df = _load_csv(output_dir / "weather.csv", WEATHER_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ── Combined extractor ────────────────────────────────────────────────────────

def extract_all(
    output_dir: Path = OUTPUT_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read all four CSVs and return (assets, sensor_readings, incidents, weather)."""
    assets_df = extract_assets(output_dir)
    sensor_df = extract_sensor_readings(output_dir)
    incidents_df = extract_incidents(output_dir)
    weather_df = extract_weather(output_dir)
    return assets_df, sensor_df, incidents_df, weather_df


# ── Script entry point ────────────────────────────────────────────────────────

def main() -> None:
    assets_df, sensor_df, incidents_df, weather_df = extract_all()
    logger.info(
        "Extract complete — assets=%d, sensor_rows=%d, incidents=%d, weather=%d",
        len(assets_df), len(sensor_df), len(incidents_df), len(weather_df),
    )


if __name__ == "__main__":
    main()
