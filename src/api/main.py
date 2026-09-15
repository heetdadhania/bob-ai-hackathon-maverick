"""
api/main.py

FastAPI application for the Grid Guard power-outage prediction service.

Endpoints:
    GET /health       — liveness check + DB connectivity
    GET /predictions  — runs the ML pipeline; returns per-asset failure
                        probabilities
    GET /rankings     — runs the ML pipeline; returns assets ranked by
                        severity score (failure_prob × customers × tier weight)
    GET /plan         — runs the ML pipeline and calls IBM watsonx.ai to
                        generate a prioritised maintenance/crew plan

Run:
    uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
import os
from typing import Any

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# ── Config ────────────────────────────────────────────────────────────────────

# Read lazily so that importing this module doesn't crash when the environment
# isn't configured yet (e.g. during test collection or type-checking).
DB_URL: str = os.environ.get("NEON_DATABASE_URL", "")
TOP_N_DEFAULT: int = int(os.environ.get("TOP_N_ASSETS", "10"))

# CORS: allow the Streamlit dashboard origin (and localhost variants for dev)
_API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
_DASHBOARD_ORIGIN: str = os.environ.get("DASHBOARD_ORIGIN", "http://localhost:8501")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Grid Guard API",
    version="1.0.0",
    description="Power outage prediction and maintenance plan API for grid operators.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_DASHBOARD_ORIGIN],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Pydantic response models ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    db: str = Field(..., examples=["connected"])


class PredictionItem(BaseModel):
    asset_id: str
    failure_probability: float = Field(..., ge=0.0, le=1.0)


class PredictionsResponse(BaseModel):
    count: int
    predictions: list[PredictionItem]


class RankedAsset(BaseModel):
    rank: int
    asset_id: str
    failure_probability: float = Field(..., ge=0.0, le=1.0)
    severity_score: float
    criticality_tier: int
    customers_served: int
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class RankingsResponse(BaseModel):
    count: int
    rankings: list[RankedAsset]


class PlanResponse(BaseModel):
    asset_count: int
    plan: str


# ── DB helper ─────────────────────────────────────────────────────────────────

def _db_connect() -> psycopg2.extensions.connection:
    """Open a Postgres connection; raises HTTP 503 if unreachable."""
    url = os.environ.get("NEON_DATABASE_URL", DB_URL)
    if not url:
        raise HTTPException(
            status_code=503,
            detail="NEON_DATABASE_URL is not configured.",
        )
    try:
        return psycopg2.connect(url)
    except psycopg2.OperationalError as exc:
        raise HTTPException(
            status_code=503, detail=f"Database unreachable: {exc}"
        ) from exc


# ── ML pipeline helper ────────────────────────────────────────────────────────

def _run_pipeline() -> pd.DataFrame:
    """Run the full ML inference pipeline and return the ranked DataFrame.

    Calls ml.predict.main() which:
      1. Loads model artefacts
      2. Builds live feature vectors from the DB
      3. Scores every asset with the XGBoost model
      4. Computes severity scores and sorts descending
      5. Persists results to risk_scores table

    The returned DataFrame contains at minimum:
        asset_id, failure_probability, severity_score,
        criticality_tier, customers_served, rank

    Region is fetched in a separate lightweight join and merged in here so
    that generate_maintenance_plan() receives its required columns.

    Raises HTTPException(502) on any pipeline or DB error.
    """
    try:
        from ml.predict import main as predict_main  # noqa: PLC0415
        ranked_df: pd.DataFrame = predict_main()
    except Exception as exc:
        logger.exception("ML pipeline failed: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"ML pipeline error: {exc}"
        ) from exc

    # Enrich with region and coordinates (not merged by rank_by_severity)
    try:
        conn = _db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT asset_id, region, lat, lon FROM assets")
                geo_rows = cur.fetchall()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Failed to fetch asset geo data: {exc}"
        ) from exc

    geo_df = pd.DataFrame(geo_rows, columns=["asset_id", "region", "lat", "lon"])
    ranked_df = ranked_df.merge(geo_df, on="asset_id", how="left")
    # Rename to the canonical field names expected by the dashboard
    ranked_df = ranked_df.rename(columns={"lat": "latitude", "lon": "longitude"})

    return ranked_df


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health() -> Any:
    """Liveness check — verifies DB connectivity without running the pipeline."""
    conn = _db_connect()
    conn.close()
    return {"status": "ok", "db": "connected"}


@app.get("/predictions", response_model=PredictionsResponse)
def get_predictions(
    top_n: int = Query(default=TOP_N_DEFAULT, ge=1, le=500),
) -> Any:
    """Run the ML pipeline and return per-asset failure probabilities.

    Triggers a full model inference pass. Use /rankings for severity-ordered
    results or /plan for the generated maintenance plan.
    """
    ranked_df = _run_pipeline()

    predictions = (
        ranked_df[["asset_id", "failure_probability"]]
        .sort_values("failure_probability", ascending=False)
        .head(top_n)
    )

    return {
        "count": len(predictions),
        "predictions": predictions.to_dict(orient="records"),
    }


@app.get("/rankings", response_model=RankingsResponse)
def get_rankings(
    top_n: int = Query(default=TOP_N_DEFAULT, ge=1, le=500),
) -> Any:
    """Run the ML pipeline and return assets ranked by grid-impact severity.

    severity_score = failure_probability × customers_served × criticality_weight
    """
    ranked_df = _run_pipeline()

    top = ranked_df.head(top_n)

    rankings: list[dict] = []
    for _, row in top.iterrows():
        lat = row.get("latitude")
        lon = row.get("longitude")
        rankings.append({
            "rank": int(row["rank"]),
            "asset_id": str(row["asset_id"]),
            "failure_probability": float(row["failure_probability"]),
            "severity_score": float(row["severity_score"]),
            "criticality_tier": int(row["criticality_tier"]),
            "customers_served": int(row.get("customers_served", 0)),
            "region": row.get("region"),
            "latitude": float(lat) if pd.notna(lat) else None,
            "longitude": float(lon) if pd.notna(lon) else None,
        })

    return {"count": len(rankings), "rankings": rankings}


@app.get("/plan", response_model=PlanResponse)
def get_plan(
    top_n: int = Query(default=TOP_N_DEFAULT, ge=1, le=500),
) -> Any:
    """Run the ML pipeline then call IBM watsonx.ai to generate a maintenance plan.

    Returns a prioritised, plain-English plan for the top-N at-risk assets.
    Raises HTTP 502 if either the ML pipeline or the watsonx.ai call fails.
    """
    ranked_df = _run_pipeline()

    try:
        from llm.generate_plan import generate_maintenance_plan  # noqa: PLC0415
        plan_text = generate_maintenance_plan(ranked_df, top_n=top_n)
    except (RuntimeError, ValueError) as exc:
        logger.exception("Plan generation failed: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"Plan generation error: {exc}"
        ) from exc

    asset_count = min(top_n, len(ranked_df))
    return {"asset_count": asset_count, "plan": plan_text}
