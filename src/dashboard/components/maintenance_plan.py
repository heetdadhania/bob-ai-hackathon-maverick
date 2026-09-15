"""
dashboard/components/maintenance_plan.py

Renders the IBM Bob / watsonx.ai generated maintenance plan panel.

render_maintenance_plan(plan_text) handles three states:
  - Empty string  → clear "not yet generated" prompt (no fake content)
  - Non-empty str → formatted plan in a styled card
  - Error marker  → visible error banner (plan_text starting with "ERROR:")

The loading state is managed by the caller (app.py) via st.spinner before
calling this function, so this component only ever receives the final value.
"""

import streamlit as st

from dashboard.config import PLAN_ACCENT_COLOUR, PLAN_ERROR_PREFIX


def _render_error(message: str) -> None:
    st.error(
        f"**Plan generation failed.** {message}\n\n"
        "Check that the API server is running and that the watsonx.ai "
        "credentials in `.env` are correct, then try again.",
        icon="🔴",
    )


def _render_plan(plan_text: str) -> None:
    """Render the plan text in a styled card."""
    safe = (
        plan_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    st.markdown(
        f"<div style='"
        f"background:#f7f8fa;"
        f"border:1px solid #e5e7eb;"
        f"border-left:4px solid {PLAN_ACCENT_COLOUR};"
        f"border-radius:6px;"
        f"padding:1.2rem 1.6rem;"
        f"font-size:0.95rem;"
        f"line-height:1.75;"
        f"white-space:pre-wrap;"
        f"'>{safe}</div>",
        unsafe_allow_html=True,
    )

    st.download_button(
        label="⬇ Download plan as .txt",
        data=plan_text,
        file_name="grid_guard_maintenance_plan.txt",
        mime="text/plain",
        use_container_width=False,
    )


def render_maintenance_plan(plan_text: str) -> None:
    """Display the watsonx.ai maintenance plan, an error banner, or a prompt.

    Parameters
    ----------
    plan_text:
        The value stored in st.session_state["plan"].
        - ""             → not yet generated; show an informational prompt.
        - "ERROR: …"     → generation failed; show an error banner with the
                           reason. Never show a fake or placeholder plan.
        - Any other str  → render the formatted plan card.
    """
    if not plan_text:
        st.info(
            "No maintenance plan has been generated yet. "
            "Click **🤖 Generate maintenance plan** in the sidebar to produce "
            "a prioritised crew dispatch plan for the top-ranked at-risk assets."
        )
        return

    if plan_text.startswith(PLAN_ERROR_PREFIX):
        _render_error(plan_text[len(PLAN_ERROR_PREFIX):].strip())
        return

    _render_plan(plan_text)
