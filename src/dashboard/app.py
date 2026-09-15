"""
dashboard/app.py

Grid Guard — Streamlit operator dashboard.

Layout:
  - Sidebar: controls (top-N slider, refresh button, API status)
  - Main area:
      Tab 1: Asset Risk Map  + Ranked Risk Table
      Tab 2: Maintenance Plan (IBM Bob / watsonx.ai output)

Run:
    streamlit run dashboard/app.py
"""

import streamlit as st

from dashboard.components.asset_map import render_asset_map
from dashboard.components.maintenance_plan import render_maintenance_plan
from dashboard.components.risk_table import render_risk_table
from dashboard.config import TOP_N_ASSETS
from dashboard.utils.api_client import fetch_plan, fetch_risk, health_check

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Grid Guard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚡ Grid Guard")
    st.caption("Power Outage Prediction & Grid Equipment Failure Advisor")
    st.divider()

    api_ok = health_check()
    if api_ok:
        st.success("API connected", icon="✅")
    else:
        st.error("API unreachable — start the FastAPI server first.", icon="🔴")

    top_n = st.slider(
        "Top N assets to display",
        min_value=5,
        max_value=50,
        value=TOP_N_ASSETS,
        step=5,
    )

    refresh = st.button("🔄 Refresh data", use_container_width=True)
    generate_plan_btn = st.button(
        "🤖 Generate maintenance plan", use_container_width=True
    )

    st.divider()
    st.caption("Team Maverick · Bobathon · Track: AI")

# ── Session state ─────────────────────────────────────────────────────────────

if "assets" not in st.session_state:
    st.session_state["assets"] = []
if "plan" not in st.session_state:
    st.session_state["plan"] = ""

if refresh or not st.session_state["assets"]:
    if api_ok:
        with st.spinner("Loading risk data..."):
            try:
                st.session_state["assets"] = fetch_risk(top_n)
            except RuntimeError as e:
                st.error(str(e))
    else:
        st.warning("Cannot fetch data: API is not reachable.")

if generate_plan_btn:
    if api_ok:
        with st.spinner("Generating maintenance plan via IBM Bob / watsonx.ai..."):
            try:
                st.session_state["plan"] = fetch_plan(top_n)
            except RuntimeError as e:
                st.error(str(e))
    else:
        st.warning("Cannot generate plan: API is not reachable.")

# ── Main content ──────────────────────────────────────────────────────────────

st.header("Grid Guard — Asset Risk Dashboard")

assets = st.session_state["assets"]

if assets:
    col1, col2, col3 = st.columns(3)
    col1.metric("Assets monitored", len(assets))
    high_risk = sum(1 for a in assets if a.get("failure_probability", 0) >= 0.7)
    col2.metric("High-risk assets (≥70%)", high_risk)
    top_severity = max((a.get("severity_score", 0) for a in assets), default=0)
    col3.metric("Highest severity score", f"{top_severity:.2f}")
    st.divider()

tab_map, tab_plan = st.tabs(["📍 Risk Map & Rankings", "📋 Maintenance Plan"])

with tab_map:
    if assets:
        st.subheader("Asset Risk Map")
        render_asset_map(assets)
        st.subheader("Ranked Risk Table")
        render_risk_table(assets)
    else:
        st.info("Click **Refresh data** in the sidebar to load asset risk scores.")

with tab_plan:
    st.subheader("IBM Bob / watsonx.ai — Maintenance & Crew Dispatch Plan")
    if st.session_state["plan"]:
        render_maintenance_plan(st.session_state["plan"])
    else:
        st.info(
            "Click **Generate maintenance plan** in the sidebar to produce a "
            "plain-English crew dispatch plan for the top-ranked at-risk assets."
        )
