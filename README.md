# Grid Guard — Power Outage Prediction & Grid Equipment Failure Advisor

> Predict grid failures before they happen. Dispatch crews before the lights go out.

---

## Team

| | |
|---|---|
| **Team** | Maverick |
| **Track** | AI |
| **Lead** | Heet Dadhaniya - 25msit023@charusat.edu.in |
| **Members** | Axit Dudhat, Aryan Jivani, Parth Vora |

---

## Problem Statement

Utility operators depend on calendar-based maintenance schedules that ignore the
failure signatures already present in asset sensor data weeks before a fault occurs.
Weather events, historical incident records, and live telemetry are never correlated
in a single place or in time to act. The result is reactive, costly blackouts that
better decision support could prevent.

For a full analysis of the problem, see [`docs/problem-statement.md`](docs/problem-statement.md).

---

## Solution

Grid Guard fuses asset sensor telemetry, multi-day weather forecasts, and historical
outage records into a unified data pipeline backed by Neon Postgres. An XGBoost model
scores each asset's failure probability; assets are then ranked by grid-impact
severity (probability × customers served × criticality tier). IBM Bob, powered by
watsonx.ai, consumes the ranked list and produces a prioritised, plain-English
maintenance and crew pre-positioning plan — from raw data to actionable field orders
in a single workflow.

For the full solution walkthrough see [`docs/solution-overview.md`](docs/solution-overview.md).
For the architecture diagram and component breakdown see [`docs/architecture.md`](docs/architecture.md).

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
- **Interactive Streamlit dashboard** — at-risk asset map, ranked risk table, and
  Bob-generated recommended actions in one operator view.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10 / 3.11 |
| Data storage | [Neon](https://neon.tech) (serverless Postgres) via SQLAlchemy |
| ML model | XGBoost, scikit-learn, SHAP |
| API layer | FastAPI + Uvicorn |
| Frontend | Streamlit, Plotly |
| AI / LLM | IBM watsonx.ai via `ibm-watsonx-ai` SDK (IBM Bob) |
| Weather data | [Open-Meteo](https://open-meteo.com) API (free, no account required) |
| Data processing | pandas, numpy, scipy |

---

## Repository Structure

```
bob-ai-hackathon-maverick/
│
├── submission.yaml              ← Structured submission metadata
├── README.md                    ← This file
│
├── src/
│   ├── api/                     ← FastAPI REST endpoints (/risk, /plan, /health)
│   ├── dashboard/               ← Streamlit operator dashboard
│   ├── data_generation/         ← Synthetic asset/sensor/incident data + weather fetch
│   ├── etl/                     ← ETL pipeline and schema.sql
│   ├── feature_engineering/     ← Rolling stats, z-scores, weather joins
│   ├── llm/                     ← IBM Bob / watsonx.ai plan generation
│   ├── ml/                      ← XGBoost training and inference
│   ├── models/                  ← Saved model artefacts
│   ├── .env.example             ← Template for environment variables
│   └── requirements.txt         ← Python dependencies
│
├── docs/
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
│
├── demo/
│   ├── demo-video-link.txt
│   ├── live-demo-url.txt
│   └── screenshots/
│
└── presentation/
```

---

## How to Run

Full prerequisites, environment variable reference, and troubleshooting are in
[`docs/setup-guide.md`](docs/setup-guide.md).

**Quick start:**

```bash
# 1. Clone the repo and create a virtual environment
git clone https://github.com/your-org/bob-ai-hackathon-maverick.git
cd bob-ai-hackathon-maverick
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r src/requirements.txt

# 3. Configure credentials
cp src/.env.example src/.env
# Edit src/.env — fill in NEON_DATABASE_URL, WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL

# 4. Initialise database schema
psql "$NEON_DATABASE_URL" -f src/etl/schema.sql

# 5. Run the full data pipeline
python src/data_generation/generate_fake_data.py
python src/data_generation/fetch_weather.py
python src/feature_engineering/build_features.py
python src/ml/train_model.py
python src/ml/predict.py

# 6. Start the API and dashboard (two terminals)
cd src && uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
cd src && streamlit run dashboard/app.py
```

Dashboard: `http://localhost:8501` · API: `http://localhost:8000`

---

## Demo

| Resource | Location |
|---|---|
| Demo video | [`demo/demo-video-link.txt`](demo/demo-video-link.txt) |
| Live demo URL | [`demo/live-demo-url.txt`](demo/live-demo-url.txt) |
| Screenshots | [`demo/screenshots/`](demo/screenshots/) |
| Presentation | [`presentation/`](presentation/) |

---

## Known Limitations

- **Synthetic sensor data** — asset telemetry is generated from statistical
  distributions; real utility SCADA feeds have not been integrated.
- **Greedy dispatch ranking** — crew assignments are ordered by severity score; no
  full route-optimisation solver is included.
- **Limited incident history** — the training dataset contains a small synthetic
  sample of historical outage records, which constrains model generalisation.
- **No live weather-alert integration** — weather data is fetched on a scheduled
  basis via Open-Meteo; real-time severe-weather alerts (e.g. NWS) are not wired in.
- **Demo environment sizing** — the shared Neon Postgres instance is not sized for
  production load volumes.

---

## What We're Most Proud Of

The end-to-end pipeline — from raw multi-source data ingestion through SHAP-explainable
risk scoring to an IBM Bob–generated, plain-English crew dispatch plan — runs as a
single coherent workflow with no manual hand-off between stages. The SHAP explainability
layer is the part we'd most like judges to evaluate: rather than presenting a black-box
probability number, every flagged asset comes with the specific sensor readings and
weather context that drove its score, and IBM Bob names those reasons explicitly in the
maintenance plan it generates.

---

## Documentation

| Document | Description |
|---|---|
| [`docs/problem-statement.md`](docs/problem-statement.md) | Deep-dive on the grid maintenance problem, affected stakeholders, and scale |
| [`docs/solution-overview.md`](docs/solution-overview.md) | How Grid Guard works — core mechanism, design decisions, user experience |
| [`docs/architecture.md`](docs/architecture.md) | System diagram, component table, end-to-end data walkthrough |
| [`docs/setup-guide.md`](docs/setup-guide.md) | Full setup, configuration, and troubleshooting guide |
