"""
dashboard/components/maintenance_plan.py

Renders the IBM Bob / watsonx.ai generated maintenance plan panel.
"""

import streamlit as st


def render_maintenance_plan(plan: str) -> None:
    """Display the generated maintenance plan in a styled panel."""
    if not plan:
        st.info(
            "No maintenance plan available. "
            "Ensure the API is running and risk scores have been computed."
        )
        return

    st.markdown(
        "<div style='"
        "background:#f7f8fa;"
        "border:1px solid #e5e7eb;"
        "border-left:4px solid #3b82d4;"
        "border-radius:6px;"
        "padding:1.2rem 1.4rem;"
        "font-size:0.95rem;"
        "line-height:1.7;"
        "white-space:pre-wrap;"
        "'>"
        + plan.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\n", "<br>")
        + "</div>",
        unsafe_allow_html=True,
    )
