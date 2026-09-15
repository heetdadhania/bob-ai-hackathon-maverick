"""
llm/generate_plan.py

Builds a structured prompt from the top-ranked risk_scores rows and calls IBM
watsonx.ai (via ibm-watsonx-ai SDK) to generate a prioritised, plain-English
maintenance and crew pre-positioning plan.

Raises RuntimeError if the watsonx.ai call fails — no silent fallbacks.

Run standalone:
    python llm/generate_plan.py
"""

import json
import logging
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

DB_URL: str = os.environ["NEON_DATABASE_URL"]
WATSONX_API_KEY: str = os.environ["WATSONX_API_KEY"]
WATSONX_PROJECT_ID: str = os.environ["WATSONX_PROJECT_ID"]
WATSONX_URL: str = os.environ["WATSONX_URL"]
WATSONX_MODEL_ID: str = os.environ["WATSONX_MODEL_ID"]
TOP_N_ASSETS: int = int(os.environ["TOP_N_ASSETS"])

_SYSTEM_PROMPT = """\
You are a grid reliability advisor. You will be given a ranked list of power grid \
assets that are at risk of failure. For each asset you have: its asset ID, type, \
failure probability, severity score, the top sensor readings driving the risk, and \
the upcoming weather forecast context.

Your job is to write a prioritised, plain-English maintenance and crew \
pre-positioning plan. For each asset:
1. Name the asset and state its priority rank.
2. Explain in one sentence why it is flagged (sensor trend + weather context).
3. Recommend a specific action: inspect, targeted replacement, pre-staged spares, \
or load shedding.

Be direct and practical. Use numbered steps. Do not repeat raw numbers \
verbatim — translate them into operational meaning.\
"""


def fetch_ranked_assets(
    conn: psycopg2.extensions.connection, top_n: int
) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                rs.asset_id,
                rs.rank,
                rs.failure_probability,
                rs.severity_score,
                rs.top_features,
                a.asset_type,
                a.criticality_tier,
                a.customers_served,
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
        return [dict(r) for r in cur.fetchall()]


def _build_prompt(assets: list[dict]) -> str:
    lines = ["Ranked at-risk assets:\n"]
    for asset in assets:
        top_feats = asset.get("top_features") or []
        if isinstance(top_feats, str):
            top_feats = json.loads(top_feats)
        feat_str = "; ".join(
            f"{f['feature']} (SHAP {f['shap_value']:+.3f})" for f in top_feats
        )
        weather_str = (
            f"forecast max temp {asset['forecast_temp_max_48h']:.1f}°C, "
            f"wind {asset['forecast_wind_max_48h']:.1f} km/h"
            if asset.get("forecast_temp_max_48h") is not None
            else "no weather data"
        )
        lines.append(
            f"Rank {asset['rank']} — {asset['asset_id']} "
            f"({asset['asset_type']}, tier {asset['criticality_tier']}, "
            f"{asset['customers_served']:,} customers)\n"
            f"  Failure probability: {asset['failure_probability']:.1%}  "
            f"Severity score: {asset['severity_score']:.2f}\n"
            f"  Key signals: {feat_str}\n"
            f"  Weather (next 48 h): {weather_str}\n"
            f"  Days since last incident: "
            f"{asset.get('days_since_last_incident', 'unknown')}\n"
        )
    lines.append("\nWrite the maintenance and crew pre-positioning plan:")
    return "\n".join(lines)


def generate_plan(assets: list[dict]) -> str:
    """Call watsonx.ai and return the generated plan text.

    Raises RuntimeError on any API failure — never returns a hardcoded fallback.
    """
    credentials = Credentials(api_key=WATSONX_API_KEY, url=WATSONX_URL)
    client = APIClient(credentials)

    model = ModelInference(
        model_id=WATSONX_MODEL_ID,
        api_client=client,
        project_id=WATSONX_PROJECT_ID,
        params={
            GenParams.MAX_NEW_TOKENS: 1024,
            GenParams.TEMPERATURE: 0.2,
            GenParams.REPETITION_PENALTY: 1.1,
        },
    )

    full_prompt = f"{_SYSTEM_PROMPT}\n\n{_build_prompt(assets)}"
    try:
        response = model.generate_text(prompt=full_prompt)
    except Exception as exc:
        raise RuntimeError(
            f"watsonx.ai plan generation failed: {exc}"
        ) from exc

    if not response:
        raise RuntimeError(
            "watsonx.ai returned an empty response — check model ID and project ID."
        )

    return response.strip()


def main() -> None:
    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as exc:
        raise RuntimeError(f"Cannot connect to Neon Postgres: {exc}") from exc

    try:
        assets = fetch_ranked_assets(conn, TOP_N_ASSETS)
    finally:
        conn.close()

    if not assets:
        raise RuntimeError(
            "No risk scores found in the database. Run ml/predict.py first."
        )

    logger.info("Generating plan for top %d assets...", len(assets))
    plan = generate_plan(assets)
    logger.info("Plan generated (%d chars).", len(plan))
    print(plan)


if __name__ == "__main__":
    main()
