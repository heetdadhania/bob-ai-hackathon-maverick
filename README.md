# Grid Guard — Power Outage Prediction & Grid Equipment Failure Advisor

> Predict grid failures before they happen. Dispatch crews before the lights go out.

---

## Team

| | |
|---|---|
| **Team** | Maverick |
| **Track** | AI |
| **Lead** | Heet Dadhaniya |
| **Members** | Axit Dudhat, Aryan Jivani, Parth Vora |

---

## Problem Statement

Utility operators depend on calendar-based maintenance schedules that ignore the
failure signatures already present in asset sensor data weeks before a fault occurs.
Weather events, historical incident records, and live telemetry are never correlated
in a single place or in time to act. The result is reactive, costly blackouts that
better decision support could prevent.

---

## Solution

Grid Guard fuses asset sensor telemetry, multi-day weather forecasts, and historical
outage records into a unified data pipeline backed by Neon Postgres. An XGBoost model
scores each asset's failure probability; assets are then ranked by grid-impact
severity (probability × customers served × criticality tier). IBM Bob, powered by
watsonx.ai, consumes the ranked list and produces a prioritised, plain-English
maintenance and crew pre-positioning plan — from raw data to actionable field orders
in a single workflow.

For a full architecture walkthrough see [`docs/architecture.md`](docs/architecture.md).

---

## Key Features

- **Multi-source data fusion** — sensor telemetry, Open-Meteo weather forecasts, and
  incident history ingested and joined in a Neon Postgres pipeline.
- **XGBoost failure-risk model** — per-asset probability scores with SHAP
  feature-importance so operators understand *why* an asset is flagged.
- **Grid-impact severity ranking** — composite score (failure probability × customers
  served × criticality tier) surfaces the highest-consequence assets first.
- **IBM Bob / watsonx.ai maintenance plan** — natural-language, prioritised
  maintenance schedule and crew dispatch recommendation generated automatically.
- **Interactive Streamlit dashboard** — at-risk asset map, ranked table, and
  recommended actions in one view.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data storage | [Neon](https://neon.tech) (serverless Postgres) |
| ML model | XGBoost, scikit-learn, SHAP |
| API layer | FastAPI |
| Frontend | Streamlit |
| AI / LLM | IBM watsonx.ai via IBM Bob |
| Weather data | Open-Meteo API |
| Data processing | Python — pandas, numpy |

---

## How to Run

Full prerequisites and configuration are in [`docs/setup-guide.md`](docs/setup-guide.md).

Quick start:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the data pipeline and train the model
python pipeline/run_pipeline.py

# 3. Launch the Streamlit dashboard
streamlit run app/dashboard.py
```

---

## Demo

| Resource | Location |
|---|---|
| Demo video | See [`demo/demo-video-link.txt`](demo/demo-video-link.txt) |
| Live demo URL | See [`demo/live-demo-url.txt`](demo/live-demo-url.txt) |
| Screenshots | [`demo/screenshots/`](demo/screenshots/) |

---

## Known Limitations

- **Synthetic sensor data** — asset telemetry is generated from statistical
  distributions; real utility SCADA feeds have not been integrated.
- **Limited incident history** — the training dataset contains a small sample of
  historical outage records, which constrains model generalisation.
- **No live weather-alert integration** — weather data is fetched on a scheduled
  basis via Open-Meteo; real-time severe-weather alerts (e.g. NWS) are not yet wired
  in.

---

## What We're Most Proud Of

The end-to-end pipeline — from raw multi-source data ingestion through risk scoring
to an IBM Bob–generated, plain-English crew dispatch plan — runs as a single coherent
workflow. Bridging a trained ML model directly to an LLM-powered advisory output,
with no manual hand-off, is the core innovation we'd most like judges to evaluate.
