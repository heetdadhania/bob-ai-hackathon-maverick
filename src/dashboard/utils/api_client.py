"""
dashboard/utils/api_client.py

Thin wrapper around the Grid Guard FastAPI endpoints.
Returns Python dicts/lists; raises RuntimeError on non-2xx or connection errors.
"""

import logging

import requests

from dashboard.config import API_BASE_URL, API_TIMEOUT_S, PLAN_TIMEOUT_S

logger = logging.getLogger(__name__)


def fetch_risk(top_n: int | None = None) -> list[dict]:
    """Fetch ranked risk scores from GET /risk."""
    params = {"top_n": top_n} if top_n else {}
    try:
        resp = requests.get(
            f"{API_BASE_URL}/risk", params=params, timeout=API_TIMEOUT_S
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Cannot reach Grid Guard API at {API_BASE_URL}: {exc}") from exc
    if not resp.ok:
        raise RuntimeError(f"Risk endpoint returned {resp.status_code}: {resp.text}")
    return resp.json()


def fetch_plan(top_n: int | None = None) -> str:
    """Fetch the Bob-generated maintenance plan from GET /plan."""
    params = {"top_n": top_n} if top_n else {}
    try:
        resp = requests.get(
            f"{API_BASE_URL}/plan", params=params, timeout=PLAN_TIMEOUT_S
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Cannot reach Grid Guard API at {API_BASE_URL}: {exc}") from exc
    if not resp.ok:
        raise RuntimeError(f"Plan endpoint returned {resp.status_code}: {resp.text}")
    plan = resp.json().get("plan", "")
    if not plan:
        raise RuntimeError("API returned an empty plan — check watsonx.ai configuration.")
    return plan


def health_check() -> bool:
    """Return True if the API is reachable and healthy, False otherwise."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return resp.ok
    except requests.exceptions.ConnectionError:
        return False
