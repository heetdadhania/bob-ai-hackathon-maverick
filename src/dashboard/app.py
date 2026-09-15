"""
dashboard/app.py

Grid Guard — Power Outage Prediction & Grid Equipment Failure Advisor.

Layout
------
Sidebar:
  - API health indicator
  - Top-N slider
  - Refresh data button
  - Generate maintenance plan button

Main area:
  KPI row (assets monitored / high-risk count / max severity)
  Tab 1 — 📍 Risk Map & Rankings
    Asset risk map (colour-coded by severity tier)
    Ranked risk table (filterable by region and tier)
  Tab 2 — 📋 Maintenance Plan
    IBM Bob / watsonx.ai generated plan

Session state keys
------------------
  rankings  list[dict]  — latest GET /rankings response ([] when not yet loaded)
  plan      str         — latest GET /plan response ("" = not yet generated,
                          "ERROR: …" = failed generation)

Run:
    streamlit run dashboard/app.py
"""

import streamlit as st

from dashboard.components.asset_map import render_asset_map
from dashboard.components.maintenance_plan import render_maintenance_plan
from dashboard.components.risk_table import render_risk_table
from dashboard.config import HIGH_RISK_PROBABILITY, PLAN_ERROR_PREFIX, SEVERITY_HIGH, TOP_N_ASSETS
from dashboard.utils.api_client import get_plan, get_rankings, health_check

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Grid Guard — Power Outage Prediction & Grid Equipment Failure Advisor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state initialisation ──────────────────────────────────────────────

if "rankings" not in st.session_state:
    st.session_state["rankings"] = []
if "plan" not in st.session_state:
    st.session_state["plan"] = ""

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚡ Grid Guard")
    st.caption("Power Outage Prediction & Grid Equipment Failure Advisor")
    st.divider()

    api_ok = health_check()
    if api_ok:
        st.success("API connected", icon="✅")
    else:
        st.error(
            "API unreachable — start the FastAPI server first.", icon="🔴"
        )

    top_n: int = st.slider(
        "Top N assets",
        min_value=5,
        max_value=50,
        value=TOP_N_ASSETS,
        step=5,
        help="Number of highest-risk assets to display on the map and in the table.",
    )

    refresh_btn = st.button("🔄 Refresh data", use_container_width=True)
    generate_plan_btn = st.button(
        "🤖 Generate maintenance plan",
        use_container_width=True,
        disabled=not api_ok,
        help="Calls IBM watsonx.ai to produce a prioritised crew dispatch plan.",
    )

    st.divider()
    st.caption("Team Maverick · Bobathon · Track: AI")

# ── Data fetching ─────────────────────────────────────────────────────────────

# Auto-load on first render; re-load when the user clicks Refresh.
if refresh_btn or not st.session_state["rankings"]:
    if api_ok:
        with st.spinner("Loading risk rankings…"):
            rankings = get_rankings(top_n)
        if rankings:
            st.session_state["rankings"] = rankings
            # Clear a stale plan when data is refreshed so it can't mislead.
            st.session_state["plan"] = ""
        else:
            st.error(
                "Rankings could not be loaded. "
                "The ML pipeline may still be running — check the API logs.",
                icon="⚠️",
            )
    else:
        st.warning("Cannot fetch rankings: API is not reachable.")

if generate_plan_btn:
    with st.spinner(
        "Generating maintenance plan via IBM Bob / watsonx.ai — "
        "this may take up to a minute…"
    ):
        result = get_plan(top_n)
    if result:
        st.session_state["plan"] = result
    else:
        st.session_state["plan"] = (
            f"{PLAN_ERROR_PREFIX} The API returned an empty plan. "
            "Verify watsonx.ai credentials in .env and try again."
        )

# ── KPI row ───────────────────────────────────────────────────────────────────

rankings: list[dict] = st.session_state["rankings"]

st.title("Grid Guard — Asset Risk Dashboard")

if rankings:
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Assets monitored", len(rankings))

    high_risk = sum(
        1 for a in rankings
        if a.get("failure_probability", 0.0) >= HIGH_RISK_PROBABILITY
    )
    kpi2.metric(
        f"High-risk  (fail prob ≥ {HIGH_RISK_PROBABILITY:.0%})",
        high_risk,
        delta=None,
    )

    critical = sum(1 for a in rankings if a.get("criticality_tier") == 1)
    kpi3.metric("Tier-1 critical assets", critical)

    top_severity = max(
        (a.get("severity_score", 0.0) for a in rankings), default=0.0
    )
    severity_label = "🔴 HIGH" if top_severity >= SEVERITY_HIGH else "🟡"
    kpi4.metric("Max severity score", f"{top_severity:.2f}", delta=severity_label)

    st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_map, tab_plan = st.tabs(["📍 Risk Map & Rankings", "📋 Maintenance Plan"])

with tab_map:
    if rankings:
        st.subheader("Asset Risk Map")
        render_asset_map(rankings)

        st.subheader("Ranked Risk Table")
        render_risk_table(rankings)
    else:
        st.info(
            "No data loaded. "
            "Click **🔄 Refresh data** in the sidebar to fetch the latest risk scores."
        )

with tab_plan:
    st.subheader("IBM Bob / watsonx.ai — Maintenance & Crew Dispatch Plan")

    if not api_ok and not st.session_state["plan"]:
        st.warning(
            "The API is not reachable. Start the FastAPI server and refresh "
            "the page, then click **🤖 Generate maintenance plan**."
        )
    else:
        render_maintenance_plan(st.session_state["plan"])
