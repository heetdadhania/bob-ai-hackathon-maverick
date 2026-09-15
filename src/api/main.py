"""
api/main.py

FastAPI application exposing the Grid Guard risk scores and generated plan.

Endpoints:
    GET /health   — liveness check + DB connectivity
    GET /risk     — ranked asset risk list (from risk_scores table)
    GET /plan     — IBM Bob / watsonx.ai generated maintenance plan

Run:
    uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
"""

import json
import logging
import os
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

DB_URL: str = os.environ["NEON_DATABASE_URL"]
TOP_N_DEFAULT: int = int(os.environ["TOP_N_ASSETS"])

app = FastAPI(
    title="Grid Guard API",
    version="1.0.0",
    description="Power outage prediction and maintenance plan API for grid operators.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _get_connection() -> psycopg2.extensions.connection:
    try:
        return psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:
        raise HTTPException(
            status_code=503, detail=f"Database unreachable: {exc}"
        ) from exc


@app.get("/health")
def health() -> dict:
    """Liveness check — also verifies database connectivity."""
    conn = _get_connection()
    conn.close()
    return {"status": "ok"}


@app.get("/risk")
def get_risk(top_n: int = TOP_N_DEFAULT) -> list[dict]:
    """Return the top-n assets ranked by grid-impact severity score."""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    rs.asset_id,
                    rs.rank,
                    rs.failure_probability,
                    rs.severity_score,
                    rs.top_features,
                    rs.scored_at,
                    a.asset_type,
                    a.criticality_tier,
                    a.customers_served,
                    a.latitude,
                    a.longitude,
                    a.region,
                    fm.forecast_temp_max_48h,
                    fm.forecast_wind_max_48h,
                    fm.days_since_last_incident
                FROM risk_scores rs
                JOIN assets a USING (asset_id)
                LEFT JOIN feature_matrix fm USING (asset_id)
                ORDER BY rs.rank ASC
                LIMIT %s
                """,
                (top_n,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No risk scores found. Run ml/predict.py to score assets.",
        )

    for row in rows:
        if isinstance(row.get("top_features"), str):
            row["top_features"] = json.loads(row["top_features"])
        if isinstance(row.get("scored_at"), datetime):
            row["scored_at"] = row["scored_at"].isoformat()

    return rows


@app.get("/plan")
def get_plan(top_n: int = TOP_N_DEFAULT) -> dict:
    """Generate and return the IBM Bob / watsonx.ai maintenance plan."""
    from llm.generate_plan import fetch_ranked_assets, generate_plan  # noqa: PLC0415

    conn = _get_connection()
    try:
        assets = fetch_ranked_assets(conn, top_n)
    finally:
        conn.close()

    if not assets:
        raise HTTPException(
            status_code=404,
            detail="No risk scores found. Run ml/predict.py first.",
        )

    try:
        plan_text = generate_plan(assets)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"plan": plan_text, "asset_count": len(assets)}
