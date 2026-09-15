"""
dashboard/config.py

Centralised configuration for the Streamlit dashboard.
All values are read from environment variables (loaded via .env).
"""

import os

from dotenv import load_dotenv

load_dotenv()

API_BASE_URL: str = os.environ["API_BASE_URL"]
TOP_N_ASSETS: int = int(os.environ["TOP_N_ASSETS"])

SEVERITY_HIGH: float = float(os.environ["SEVERITY_HIGH"])
SEVERITY_MED: float = float(os.environ["SEVERITY_MED"])

MAP_STYLE: str = os.environ["MAP_STYLE"]

API_TIMEOUT_S: int = int(os.environ["API_TIMEOUT_S"])
PLAN_TIMEOUT_S: int = int(os.environ["PLAN_TIMEOUT_S"])
