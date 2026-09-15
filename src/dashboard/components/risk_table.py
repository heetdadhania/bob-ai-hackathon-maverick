"""
dashboard/components/risk_table.py

Renders the ranked risk table with SHAP feature context.
"""

import logging

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


def _format_top_features(features: list[dict] | None) -> str:
    if not features:
        return "—"
    return "; ".join(
        f"{f['feature']} ({'+' if f['shap_value'] > 0 else ''}{f['shap_value']:.3f})"
        for f in features
    )


def render_risk_table(assets: list[dict]) -> None:
    """Render the ranked asset risk table."""
    if not assets:
        st.info("No ranked assets to display.")
        return

    rows = [
        {
            "Rank": a.get("rank", "—"),
            "Asset ID": a.get("asset_id", "—"),
            "Type": a.get("asset_type", "—"),
            "Tier": a.get("criticality_tier", "—"),
            "Customers": f"{a.get('customers_served', 0):,}",
            "Fail Prob": f"{a.get('failure_probability', 0):.1%}",
            "Severity": f"{a.get('severity_score', 0):.2f}",
            "Region": a.get("region", "—"),
            "Forecast Max °C": (
                f"{a['forecast_temp_max_48h']:.1f}"
                if a.get("forecast_temp_max_48h") is not None
                else "—"
            ),
            "Key Signals (SHAP)": _format_top_features(a.get("top_features")),
        }
        for a in assets
    ]

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
