"""
data_generation/fetch_weather.py

Fetches real historical daily weather data from the Open-Meteo Archive API
(no API key required) for each of the five grid regions, then writes the
results to CSV and upserts into the Neon Postgres `weather` table.

Run:
    python data_generation/fetch_weather.py
"""

import logging
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
DB_URL: str = os.environ["NEON_DATABASE_URL"]
ARCHIVE_BASE_URL: str = os.environ["OPEN_METEO_BASE_URL"]
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "data_generation/output"))

HTTP_TIMEOUT_S: int = 30
# Open-Meteo archive lags ~5 days behind today; cap end_date accordingly
ARCHIVE_LAG_DAYS: int = 5

# ── Region coordinates ────────────────────────────────────────────────────────
# One representative (lat, lon) per region — matches the region labels used in
# generate_fake_data.py.  All coordinates are within the continental US.
REGION_COORDINATES: dict[str, tuple[float, float]] = {
    "North":   (47.60, -122.33),   # Seattle, WA
    "South":   (29.76,  -95.37),   # Houston, TX
    "East":    (40.71,  -74.01),   # New York, NY
    "West":    (34.05, -118.24),   # Los Angeles, CA
    "Central": (41.88,  -87.63),   # Chicago, IL
}

# Open-Meteo daily variable names for the archive endpoint
DAILY_VARIABLES: list[str] = [
    "temperature_2m_max",
    "precipitation_sum",
    "windspeed_10m_max",
]


# ── HTTP session with retry ───────────────────────────────────────────────────

def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# ── Core fetch function ───────────────────────────────────────────────────────

def fetch_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch daily weather from the Open-Meteo Archive API for one location.

    Returns a DataFrame with columns:
        date, temperature_max, precipitation_sum, windspeed_max

    Raises RuntimeError with a clear message on timeout, non-2xx response,
    or an empty/malformed payload.
    """
    if not start_date or not end_date:
        raise ValueError("start_date and end_date must be non-empty ISO 8601 strings")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "UTC",
    }

    session = _build_session()
    try:
        response = session.get(ARCHIVE_BASE_URL, params=params, timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError(
            f"Open-Meteo archive timed out for lat={latitude}, lon={longitude} "
            f"({start_date} → {end_date})"
        ) from exc
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Open-Meteo archive returned HTTP {exc.response.status_code} "
            f"for lat={latitude}, lon={longitude}: {exc.response.text[:200]}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Open-Meteo archive request failed for lat={latitude}, lon={longitude}: {exc}"
        ) from exc

    payload = response.json()
    daily = payload.get("daily", {})

    if not daily or not daily.get("time"):
        raise RuntimeError(
            f"Open-Meteo archive returned empty data for lat={latitude}, "
            f"lon={longitude} ({start_date} → {end_date})"
        )

    weather_df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]).date,
        "temperature_max": daily["temperature_2m_max"],
        "precipitation_sum": daily["precipitation_sum"],
        "windspeed_max": daily["windspeed_10m_max"],
    })

    return weather_df


# ── Multi-region fetch ────────────────────────────────────────────────────────

def fetch_all_regions(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch weather for every region in REGION_COORDINATES and return combined DataFrame."""
    frames: list[pd.DataFrame] = []
    for region, (lat, lon) in REGION_COORDINATES.items():
        logger.info("Fetching weather for region=%s (%s → %s)", region, start_date, end_date)
        region_df = fetch_weather(lat, lon, start_date, end_date)
        region_df.insert(0, "region", region)
        frames.append(region_df)
        logger.info("  %d rows received for region=%s", len(region_df), region)

    return pd.concat(frames, ignore_index=True)


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csv(weather_df: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "weather.csv"
    weather_df.to_csv(csv_path, index=False)
    logger.info("Weather CSV written to %s", csv_path.resolve())


# ── DB writer ─────────────────────────────────────────────────────────────────

def write_to_db(weather_df: pd.DataFrame) -> None:
    required_cols = {"region", "date", "temperature_max", "precipitation_sum", "windspeed_max"}
    if missing := required_cols - set(weather_df.columns):
        raise ValueError(f"weather_df is missing columns: {missing}")

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
                    INSERT INTO weather
                        (region, date, temperature_max, precipitation_sum, windspeed_max)
                    VALUES
                        (%(region)s, %(date)s, %(temperature_max)s,
                         %(precipitation_sum)s, %(windspeed_max)s)
                    ON CONFLICT (region, date) DO UPDATE SET
                        temperature_max   = EXCLUDED.temperature_max,
                        precipitation_sum = EXCLUDED.precipitation_sum,
                        windspeed_max     = EXCLUDED.windspeed_max
                    """,
                    weather_df.to_dict("records"),
                    page_size=500,
                )
        logger.info("Upserted %d weather rows to Neon Postgres.", len(weather_df))
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    end_date = (date.today() - timedelta(days=ARCHIVE_LAG_DAYS)).isoformat()
    start_date = (date.today() - timedelta(days=179 + ARCHIVE_LAG_DAYS)).isoformat()

    weather_df = fetch_all_regions(start_date, end_date)
    write_csv(weather_df, OUTPUT_DIR)
    write_to_db(weather_df)

    logger.info(
        "Done — %d weather rows across %d regions.",
        len(weather_df),
        weather_df["region"].nunique(),
    )


if __name__ == "__main__":
    main()
