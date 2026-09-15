"""
dashboard/components/asset_map.py

Renders the geographic asset risk map using Plotly scatter_mapbox.
Marker colour and size encode severity tier: High (red) / Medium (orange) /
Low (green), with larger markers for higher-severity assets.

A plain HTML legend is rendered below the map because Plotly's built-in
discrete legend re-orders items alphabetically; the explicit legend gives full
control over order and labels.
"""

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.config import (
    COLOUR_HIGH,
    COLOUR_LOW,
    COLOUR_MED,
    MAP_STYLE,
    SEVERITY_HIGH,
    SEVERITY_MED,
)

logger = logging.getLogger(__name__)

# Marker sizes per tier — larger = more urgent.
_SIZE: dict[str, int] = {"high": 14, "medium": 10, "low": 7}

# Human-readable tier labels for hover text and legend.
_LABEL: dict[str, str] = {
    "high":   f"High  (score ≥ {SEVERITY_HIGH})",
    "medium": f"Medium  ({SEVERITY_MED} – {SEVERITY_HIGH})",
    "low":    f"Low  (score < {SEVERITY_MED})",
}

_COLOUR: dict[str, str] = {
    "high":   COLOUR_HIGH,
    "medium": COLOUR_MED,
    "low":    COLOUR_LOW,
}

_REQUIRED_MAP_COLS = {"asset_id", "severity_score", "failure_probability",
                      "latitude", "longitude"}
_REQUIRED_FALLBACK_COLS = {"asset_id", "severity_score",
                           "failure_probability", "region"}


def _severity_tier(score: float) -> str:
    if score >= SEVERITY_HIGH:
        return "high"
    if score >= SEVERITY_MED:
        return "medium"
    return "low"


def _legend_html() -> str:
    """Return a compact inline-HTML legend strip."""
    items = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:5px;"
        f"margin-right:18px;font-size:0.82rem;color:#374151;'>"
        f"<span style='width:12px;height:12px;border-radius:50%;"
        f"background:{_COLOUR[tier]};flex-shrink:0;'></span>"
        f"{_LABEL[tier]}</span>"
        for tier in ("high", "medium", "low")
    )
    return (
        f"<div style='display:flex;flex-wrap:wrap;align-items:center;"
        f"gap:4px;padding:6px 2px 2px 2px;'>"
        f"<span style='font-size:0.82rem;font-weight:600;color:#374151;"
        f"margin-right:8px;'>Severity:</span>"
        f"{items}</div>"
    )


def _render_map(df: pd.DataFrame) -> None:
    """Render a Plotly mapbox figure with one scatter trace per severity tier."""
    fig = go.Figure()

    for tier in ("high", "medium", "low"):
        subset = df[df["_tier"] == tier]
        if subset.empty:
            continue

        hover = (
            "<b>%{customdata[0]}</b><br>"
            "Fail prob: %{customdata[1]}<br>"
            "Severity: %{customdata[2]}<br>"
            "Tier: %{customdata[3]}<br>"
            "Customers: %{customdata[4]}<br>"
            "Region: %{customdata[5]}"
            "<extra></extra>"
        )

        fig.add_trace(
            go.Scattermapbox(
                lat=subset["latitude"],
                lon=subset["longitude"],
                mode="markers",
                marker=go.scattermapbox.Marker(
                    size=_SIZE[tier],
                    color=_COLOUR[tier],
                    opacity=0.85,
                ),
                name=_LABEL[tier],
                customdata=subset[[
                    "asset_id",
                    "_prob_fmt",
                    "_sev_fmt",
                    "criticality_tier",
                    "_customers_fmt",
                    "region",
                ]].values,
                hovertemplate=hover,
            )
        )

    fig.update_layout(
        mapbox_style=MAP_STYLE,
        mapbox={"zoom": 3},
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=440,
        showlegend=False,   # replaced by the HTML legend below
        uirevision="asset_map",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_region_fallback(df: pd.DataFrame) -> None:
    """Bar chart fallback when lat/lon are absent — average severity by region."""
    st.info(
        "Latitude/longitude data is not available in the current API response. "
        "Showing average severity score by region instead."
    )
    region_avg = (
        df.groupby("region", dropna=False)["severity_score"]
        .mean()
        .sort_values(ascending=False)
        .reset_index()
    )
    region_avg.columns = ["Region", "Avg severity score"]
    st.bar_chart(region_avg.set_index("Region"))


def render_asset_map(assets: list[dict]) -> None:
    """Render the geographic asset risk map colour-coded by severity tier.

    Accepts the list[dict] returned by api_client.get_rankings().
    Required columns: asset_id, severity_score, failure_probability,
                      criticality_tier, customers_served, region.
    Optional (for full map): latitude, longitude.

    Falls back to a region-level bar chart when lat/lon are absent.
    """
    if not assets:
        st.info("No asset data available.")
        return

    df = pd.DataFrame(assets)

    missing_base = _REQUIRED_FALLBACK_COLS - set(df.columns)
    if missing_base:
        st.error(f"Asset data is missing required columns: {sorted(missing_base)}")
        logger.error("render_asset_map: missing columns %s", missing_base)
        return

    # Pre-format display columns used in hover text.
    df["_tier"] = df["severity_score"].apply(_severity_tier)
    df["_prob_fmt"] = df["failure_probability"].apply(lambda v: f"{v:.1%}")
    df["_sev_fmt"] = df["severity_score"].apply(lambda v: f"{v:.2f}")
    customers = df["customers_served"] if "customers_served" in df.columns else pd.Series(
        pd.NA, index=df.index, dtype="Float64"
    )
    df["_customers_fmt"] = customers.apply(
        lambda v: f"{int(v):,}" if pd.notna(v) else "—"
    )
    if "region" not in df.columns:
        df["region"] = "—"
    if "criticality_tier" not in df.columns:
        df["criticality_tier"] = "—"

    has_coords = {"latitude", "longitude"}.issubset(df.columns) and (
        df["latitude"].notna().any() and df["longitude"].notna().any()
    )

    if has_coords:
        _render_map(df)
    else:
        _render_region_fallback(df)

    st.markdown(_legend_html(), unsafe_allow_html=True)
