"""
dashboard/components/risk_table.py

Renders the ranked asset risk table with region and criticality-tier filters.

The table displays the columns returned by GET /rankings:
    rank, asset_id, region, failure_probability, severity_score,
    criticality_tier, customers_served

Filtering is done client-side via multiselect widgets so the API is not
re-called on every filter change.
"""

import logging

import pandas as pd
import streamlit as st

from dashboard.config import COLOUR_HIGH, COLOUR_LOW, COLOUR_MED, SEVERITY_HIGH, SEVERITY_MED

logger = logging.getLogger(__name__)

# Columns required from the rankings API response.
_REQUIRED_COLS = {
    "rank", "asset_id", "failure_probability",
    "severity_score", "criticality_tier", "customers_served",
}

# Display column order and labels.
_DISPLAY_COLS = [
    ("rank",                "Rank"),
    ("asset_id",            "Asset ID"),
    ("region",              "Region"),
    ("criticality_tier",    "Tier"),
    ("customers_served",    "Customers"),
    ("failure_probability", "Fail prob"),
    ("severity_score",      "Severity score"),
]


def _severity_badge(score: float) -> str:
    """Return a coloured HTML badge for the severity score cell."""
    if score >= SEVERITY_HIGH:
        colour, label = COLOUR_HIGH, "HIGH"
    elif score >= SEVERITY_MED:
        colour, label = COLOUR_MED, "MED"
    else:
        colour, label = COLOUR_LOW, "LOW"
    return (
        f"<span style='background:{colour};color:#fff;font-size:0.72rem;"
        f"font-weight:700;padding:1px 7px;border-radius:10px;"
        f"letter-spacing:0.03em;'>{label}</span> {score:.2f}"
    )


def _build_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a display-ready DataFrame with formatted columns."""
    out = pd.DataFrame()
    for col, label in _DISPLAY_COLS:
        if col not in df.columns:
            out[label] = "—"
            continue
        if col == "failure_probability":
            out[label] = df[col].apply(lambda v: f"{v:.1%}")
        elif col == "customers_served":
            out[label] = df[col].apply(
                lambda v: f"{int(v):,}" if pd.notna(v) else "—"
            )
        elif col == "severity_score":
            out[label] = df[col].apply(_severity_badge)
        elif col == "criticality_tier":
            out[label] = df[col].apply(lambda v: f"Tier {int(v)}" if pd.notna(v) else "—")
        else:
            out[label] = df[col]
    return out


def render_risk_table(assets: list[dict]) -> None:
    """Render a filterable ranked risk table.

    Accepts the list[dict] returned by api_client.get_rankings().
    Provides multiselect filters for region and criticality tier above the
    table; the table itself is always sorted by severity_score descending.
    """
    if not assets:
        st.info("No ranked assets to display.")
        return

    df = pd.DataFrame(assets)

    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        st.error(f"Rankings data is missing required columns: {sorted(missing)}")
        logger.error("render_risk_table: missing columns %s", missing)
        return

    if "region" not in df.columns:
        df["region"] = "—"

    # ── Filters ───────────────────────────────────────────────────────────────
    filter_col1, filter_col2 = st.columns(2)

    regions = sorted(df["region"].dropna().unique().tolist())
    selected_regions = filter_col1.multiselect(
        "Filter by region",
        options=regions,
        default=[],
        placeholder="All regions",
    )

    tiers = sorted(df["criticality_tier"].dropna().unique().tolist())
    tier_labels = {t: f"Tier {int(t)}" for t in tiers}
    selected_tiers = filter_col2.multiselect(
        "Filter by criticality tier",
        options=tiers,
        format_func=lambda t: tier_labels[t],
        default=[],
        placeholder="All tiers",
    )

    filtered = df.copy()
    if selected_regions:
        filtered = filtered[filtered["region"].isin(selected_regions)]
    if selected_tiers:
        filtered = filtered[filtered["criticality_tier"].isin(selected_tiers)]

    if filtered.empty:
        st.info("No assets match the selected filters.")
        return

    # Always display in severity descending order.
    filtered = filtered.sort_values("severity_score", ascending=False)

    display_df = _build_display_df(filtered)

    # st.dataframe renders HTML cells as plain text; use st.markdown table for
    # the badge column, falling back to plain st.dataframe on any render error.
    try:
        st.write(
            display_df.to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )
    except Exception:
        logger.warning("HTML table render failed; falling back to st.dataframe")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.caption(f"Showing {len(filtered)} of {len(df)} assets")
