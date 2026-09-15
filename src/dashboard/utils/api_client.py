"""
dashboard/utils/api_client.py

Thin HTTP wrapper around the Grid Guard FastAPI service.

Public functions
----------------
get_predictions(top_n)  -> list[dict]   GET /predictions
get_rankings(top_n)     -> list[dict]   GET /rankings
get_plan(top_n)         -> str          GET /plan
health_check()          -> bool         GET /health

On failure every function logs the error and returns an empty sentinel
([] or "") so the Streamlit UI can display a user-friendly message rather
than crashing on an unhandled exception.

Legacy aliases fetch_risk / fetch_plan are preserved for backwards
compatibility with the existing app.py call sites.
"""

import logging

import requests

from dashboard.config import API_BASE_URL, API_TIMEOUT_S, PLAN_TIMEOUT_S

logger = logging.getLogger(__name__)

# How long to wait for the /health ping before declaring the API down.
_HEALTH_TIMEOUT_S: int = 5


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get(path: str, params: dict, timeout: int) -> requests.Response | None:
    """Issue a GET request and return the Response, or None on network failure.

    Logs a warning on connection/timeout errors so the caller can return its
    sentinel without duplicating the log line.
    """
    url = f"{API_BASE_URL}{path}"
    try:
        return requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout:
        logger.warning("Request timed out after %ds: GET %s", timeout, url)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Cannot reach Grid Guard API at %s", API_BASE_URL)
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("Unexpected request error for GET %s: %s", url, exc)
        return None


def _params(top_n: int | None) -> dict:
    return {"top_n": top_n} if top_n is not None else {}


# ── Public API ────────────────────────────────────────────────────────────────

def get_predictions(top_n: int | None = None) -> list[dict]:
    """Return per-asset failure probabilities from GET /predictions.

    Response shape: [{"asset_id": str, "failure_probability": float}, ...]

    Returns an empty list on any network or server error; the caller is
    responsible for surfacing a message to the user.
    """
    resp = _get("/predictions", _params(top_n), API_TIMEOUT_S)
    if resp is None:
        return []
    if not resp.ok:
        logger.warning("/predictions returned %d: %s", resp.status_code, resp.text)
        return []
    return resp.json().get("predictions", [])


def get_rankings(top_n: int | None = None) -> list[dict]:
    """Return assets ranked by severity score from GET /rankings.

    Response shape: [{"rank": int, "asset_id": str, "failure_probability": float,
                       "severity_score": float, "criticality_tier": int,
                       "customers_served": float, "region": str | None}, ...]

    Returns an empty list on any network or server error.
    """
    resp = _get("/rankings", _params(top_n), API_TIMEOUT_S)
    if resp is None:
        return []
    if not resp.ok:
        logger.warning("/rankings returned %d: %s", resp.status_code, resp.text)
        return []
    return resp.json().get("rankings", [])


def get_plan(top_n: int | None = None) -> str:
    """Return the watsonx.ai generated maintenance plan from GET /plan.

    Response shape: {"asset_count": int, "plan": str}

    Returns an empty string on any network, server, or empty-plan error.
    """
    resp = _get("/plan", _params(top_n), PLAN_TIMEOUT_S)
    if resp is None:
        return ""
    if not resp.ok:
        logger.warning("/plan returned %d: %s", resp.status_code, resp.text)
        return ""
    plan = resp.json().get("plan", "")
    if not plan:
        logger.warning("/plan returned an empty plan body")
    return plan


def health_check() -> bool:
    """Return True if the API is reachable and healthy, False otherwise."""
    resp = _get("/health", {}, _HEALTH_TIMEOUT_S)
    return resp is not None and resp.ok


# ── Legacy aliases ────────────────────────────────────────────────────────────
# app.py imports fetch_risk and fetch_plan by these names; keep them in sync.

def fetch_risk(top_n: int | None = None) -> list[dict]:
    """Alias for get_rankings() — backwards compatibility for app.py."""
    return get_rankings(top_n)


def fetch_plan(top_n: int | None = None) -> str:
    """Alias for get_plan() — backwards compatibility for app.py."""
    return get_plan(top_n)
