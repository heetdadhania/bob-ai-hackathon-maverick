"""
dashboard/config.py

Single source of truth for all dashboard-wide configuration and constants.

All values that vary between deployments are read from environment variables
(via .env loaded by python-dotenv).  Display constants that have no reason to
change per deployment (colours, UI labels) are plain module-level constants
defined here so component files stay free of scattered magic values.

Import pattern in component files:
    from dashboard.config import API_BASE_URL, SEVERITY_HIGH, COLOUR_HIGH, ...
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ── API connection ────────────────────────────────────────────────────────────

# Required — no fallback.  Set API_BASE_URL in .env or the process environment.
API_BASE_URL: str = os.environ["API_BASE_URL"]

# Timeouts in seconds for regular data fetches vs. the slower plan generation.
API_TIMEOUT_S: int = int(os.environ.get("API_TIMEOUT_S", "30"))
PLAN_TIMEOUT_S: int = int(os.environ.get("PLAN_TIMEOUT_S", "120"))

# ── Default display parameters ────────────────────────────────────────────────

# Number of top-ranked assets shown by default in the sidebar slider.
TOP_N_ASSETS: int = int(os.environ.get("TOP_N_ASSETS", "10"))

# ── Map ───────────────────────────────────────────────────────────────────────

# Plotly mapbox style token-free tile layer.
MAP_STYLE: str = os.environ.get("MAP_STYLE", "carto-positron")

# ── Severity thresholds ───────────────────────────────────────────────────────
# These drive both map marker colouring and summary metrics in the dashboard.
# severity_score = failure_probability × customers_served × criticality_weight

# Assets with severity_score >= SEVERITY_HIGH are rendered in the "high" colour.
SEVERITY_HIGH: float = float(os.environ.get("SEVERITY_HIGH", "3.0"))

# Assets with severity_score >= SEVERITY_MED (and < SEVERITY_HIGH) are "medium".
SEVERITY_MED: float = float(os.environ.get("SEVERITY_MED", "1.0"))

# Failure-probability threshold used to count "high-risk" assets in the KPI row.
HIGH_RISK_PROBABILITY: float = float(os.environ.get("HIGH_RISK_PROBABILITY", "0.7"))

# ── Severity colour palette ───────────────────────────────────────────────────
# Hex values used consistently across map markers, table badges, and the plan
# panel accent.  Component files import these names; they never hardcode hex.

COLOUR_HIGH: str = "#dc2626"    # red   — severity >= SEVERITY_HIGH
COLOUR_MED: str = "#f97316"     # orange — SEVERITY_MED <= severity < SEVERITY_HIGH
COLOUR_LOW: str = "#16a34a"     # green  — severity < SEVERITY_MED

# Plotly color_discrete_map keyed by the tier label strings produced by
# asset_map._severity_colour().  Import this dict directly into scatter_mapbox.
SEVERITY_COLOUR_MAP: dict[str, str] = {
    "high":   COLOUR_HIGH,
    "medium": COLOUR_MED,
    "low":    COLOUR_LOW,
}

# Accent colour for the maintenance-plan panel border (matches IBM Blue).
PLAN_ACCENT_COLOUR: str = "#3b82d4"

# Sentinel prefix stored in session_state["plan"] when generation fails.
# Both app.py (writer) and maintenance_plan.py (reader) import this constant
# so the value is defined in exactly one place.
PLAN_ERROR_PREFIX: str = "ERROR:"
