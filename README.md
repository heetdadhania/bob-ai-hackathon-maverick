<<<<<<< HEAD
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
=======
# 🚀 [Your Project Title Here]

> ⚠️ **Replace everything in `[ ]` brackets with your actual content before submission.**

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | [Your Team Name] |
| **Track** | [AI / DevOps / Sustainability / Open] |
| **Team Lead** | [Name] — [email@ibm.com] |
| **Members** | [Name 1], [Name 2], [Name 3] |

---

## 🎯 Problem Statement

> In 2–3 sentences: What problem does your project solve? Who experiences this problem?

[Describe the real-world problem your project addresses. Be specific about who the user is and what pain point they face.]

---

## 💡 Solution

> In 2–3 sentences: What did you build? How does it solve the problem above?

[Describe your solution clearly. Explain the core mechanism — what makes it work.]

---

## ✨ Key Features

- **Feature 1:** [Brief description — e.g., "Real-time anomaly detection using watsonx.ai"]
- **Feature 2:** [Brief description]
- **Feature 3:** [Brief description]
- **Feature 4:** [Optional]
- **Feature 5:** [Optional]

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | [e.g., Python, TypeScript] |
| **Frameworks** | [e.g., FastAPI, React] |
| **IBM Technologies** | [e.g., watsonx.ai, IBM Bob, IBM Cloud] |
| **Databases** | [e.g., PostgreSQL, Redis] |
| **Other** | [e.g., Docker, GitHub Actions] |

---

## 📁 Repository Structure

```
├── src/                  # All source code
├── docs/                 # Written documentation
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
├── demo/                 # Demo artifacts
│   ├── screenshots/      # App screenshots
│   └── demo-video-link.txt  # Link to demo video
├── presentation/         # Slide deck
└── submission.yaml       # Structured submission metadata
>>>>>>> 1cde2c0a40b37d48e8f81ea3443fe9771099d70d
```

---

<<<<<<< HEAD
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
=======
## ⚡ How to Run

> **Copy these exact steps from your [`docs/setup-guide.md`](docs/setup-guide.md)**

```bash
# 1. Clone the repo
git clone https://github.com/[your-repo].git
cd [your-repo]

# 2. Install dependencies
[your install command here]

# 3. Configure environment
cp .env.example .env
# Edit .env with your values

# 4. Run the project
[your run command here]
```

---

## 🖥️ Demo

| Artifact | Link |
|---|---|
| 📹 Demo Video | [See demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 Live Demo | [See demo/live-demo-url.txt](demo/live-demo-url.txt) |
| 🖼️ Screenshots | [See demo/screenshots/](demo/screenshots/) |
| 📊 Presentation | [See presentation/slides.pdf](presentation/) |

---

## ⚠️ Known Limitations

> Be honest — judges appreciate transparency over overclaiming.

- [Limitation 1: e.g., "Authentication is mocked — not production-ready"]
- [Limitation 2: e.g., "Only tested on Chrome"]
- [Limitation 3: e.g., "Feature X is scaffolded but not fully implemented"]

---

## 🏅 What We're Most Proud Of

[Tell the judges what part of your submission is strongest and worth paying close attention to.]

---
>>>>>>> 1cde2c0a40b37d48e8f81ea3443fe9771099d70d
