"""
dashboard/components/asset_map.py

Renders the geographic asset risk map using Plotly scatter_mapbox.
Marker colour encodes severity tier: red (high) / orange (medium) / green (low).
"""

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.config import MAP_STYLE, SEVERITY_HIGH, SEVERITY_MED

logger = logging.getLogger(__name__)


def _severity_colour(score: float) -> str:
    if score >= SEVERITY_HIGH:
        return "red"
    if score >= SEVERITY_MED:
        return "orange"
    return "green"


def render_asset_map(assets: list[dict]) -> None:
    """Render a Plotly mapbox scatter plot of all assets coloured by severity tier."""
    if not assets:
        st.info("No asset data available.")
        return

    df = pd.DataFrame(assets)
    required_cols = {"severity_score", "asset_id", "asset_type",
                     "failure_probability", "latitude", "longitude"}
    missing = required_cols - set(df.columns)
    if missing:
        st.error(f"Asset data is missing required columns: {missing}")
        logger.error("render_asset_map: missing columns %s", missing)
        return

    df["colour"] = df["severity_score"].apply(_severity_colour)

    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        color="colour",
        color_discrete_map={"red": "#dc2626", "orange": "#f97316", "green": "#16a34a"},
        hover_name="asset_id",
        hover_data={
            "asset_type": True,
            "criticality_tier": True,
            "customers_served": True,
            "failure_probability": ":.1%",
            "severity_score": ":.2f",
            "colour": False,
            "latitude": False,
            "longitude": False,
        },
        size_max=14,
        zoom=3,
        height=420,
        mapbox_style=MAP_STYLE,
    )
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend_title_text="Severity",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=0.01,
            xanchor="right",
            x=0.99,
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
