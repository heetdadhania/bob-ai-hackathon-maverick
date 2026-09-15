# Setup Guide: Grid Guard

This guide takes you from a fresh clone of the repository to a running Grid Guard
instance with a populated database, trained model, live API, and Streamlit dashboard.
Follow every step in order.

---

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| **Python** | 3.10 or 3.11 (3.12 is untested) |
| **pip** | Bundled with Python; upgrade with `pip install --upgrade pip` |
| **Git** | Any recent version |
| **Neon account** | Free tier is sufficient — [neon.tech](https://neon.tech) |
| **IBM watsonx.ai account** | Required for plan generation — [watsonx.ai](https://www.ibm.com/watsonx) |

You do **not** need Docker, a local database, or any cloud CLI tools.

---

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/bob-ai-hackathon-maverick.git
cd bob-ai-hackathon-maverick
```

---

## 2. Create and Activate a Virtual Environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` prefixed to your prompt. All subsequent commands assume the
virtual environment is active.

---

## 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Copy the example file and fill in your credentials:

```bash
cp src/.env.example src/.env
```

Open `src/.env` in any text editor. The file contains the following variables — every
one is required:

| Variable | Description |
|---|---|
| `NEON_DATABASE_URL` | Full Postgres connection string from your Neon project dashboard (format: `postgresql://user:password@host/dbname?sslmode=require`) |
| `WATSONX_API_KEY` | IBM Cloud API key with access to your watsonx.ai project |
| `WATSONX_PROJECT_ID` | The project ID shown in your watsonx.ai project settings |
| `WATSONX_URL` | Regional watsonx.ai endpoint, e.g. `https://us-south.ml.cloud.ibm.com` |
| `OPEN_METEO_BASE_URL` | Open-Meteo forecast endpoint — default `https://api.open-meteo.com/v1/forecast` (no account required) |
| `MODEL_PATH` | Local path where the trained XGBoost model artefact will be saved, e.g. `models/xgb_grid_guard.json` |
| `API_HOST` | Host for the FastAPI server, e.g. `127.0.0.1` |
| `API_PORT` | Port for the FastAPI server, e.g. `8000` |

**Important:** `src/.env` is listed in `.gitignore` and must never be committed.
Do not paste credentials into any source file.

---

## 5. Initialise the Database Schema

Run the schema script against your Neon database. This creates the `assets`,
`sensor_readings`, `weather_forecasts`, and `incidents` tables:

Run the schema SQL against your Neon database using `psql`:

```bash
psql "$NEON_DATABASE_URL" -f src/etl/schema.sql
```

To verify the tables were created, open the Neon web console → your project →
Tables, and confirm `assets`, `sensor_readings`, `weather_forecasts`, `incidents`,
`feature_matrix`, and `risk_scores` are present.

---

## 6. Generate Synthetic Data

Populate the database with synthetic assets, sensor telemetry, and incident history:

```bash
python src/data_generation/generate_fake_data.py
```

Expected output: a summary line per table showing the number of rows inserted, e.g.:

```
Assets inserted:    50 (new)
Sensor rows inserted: 36000 (new)
Incidents inserted: 10 (new)
```

---

## 7. Fetch Weather Forecasts

Pull current multi-day forecasts from Open-Meteo for every asset location:

```bash
python src/data_generation/fetch_weather.py
```

Expected output: one confirmation line per asset location, e.g.:

```
Fetched weather for 50 assets.
```

---

## 8. Run Feature Engineering

Compute rolling statistics, rate-of-change features, and weather join columns:

```bash
python src/feature_engineering/build_features.py
```

Expected output:

```
Feature matrix computed: 50 assets → feature_matrix table updated.
```

---

## 9. Train the XGBoost Model

Train the failure-prediction classifier and write the model artefact to `MODEL_PATH`:

```bash
python src/ml/train_model.py
```

Expected output:

```
Training complete. Validation AUC: 0.XX
Model saved to models/xgb_grid_guard.json
```

A validation AUC above 0.70 is expected on the synthetic dataset. If AUC is below
0.60, re-run data generation (step 6) — occasional random seeds can produce
degenerate splits.

---

## 10. Start the FastAPI Server

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Leave this terminal running. Open a second terminal (with the virtual environment
activated) for the next step.

---

## 11. Start the Streamlit Dashboard

```bash
streamlit run dashboard/app.py
```

Streamlit will print a local URL, typically `http://localhost:8501`. Open it in your
browser.

---

## 12. Verify Everything Is Working

### API health check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok"}
```

### Risk endpoint

```bash
curl http://127.0.0.1:8000/risk
```

Expected: a JSON array of ranked assets with `asset_id`, `failure_probability`,
`severity_score`, and `top_features` fields.

### Plan endpoint

```bash
curl http://127.0.0.1:8000/plan
```

Expected: a JSON object with a `plan` string containing the Bob-generated
maintenance and crew dispatch recommendations.

### Streamlit dashboard

Open `http://localhost:8501` and confirm:

- The **asset risk map** renders with colour-coded markers.
- The **ranked risk table** shows assets sorted by severity score.
- The **maintenance plan** panel displays the generated plan text.

---

## Troubleshooting

| Error | Likely Cause | Fix |
|---|---|---|
| `could not connect to server: Connection refused` (Neon) | `NEON_DATABASE_URL` is missing, malformed, or the Neon project is paused | Check the URL in `src/.env`; wake the project in the Neon console; confirm `sslmode=require` is present in the URL |
| `KeyError: 'WATSONX_API_KEY'` | `.env` file not found or variable name misspelled | Confirm `src/.env` exists and contains `WATSONX_API_KEY=` with no extra spaces; confirm `python-dotenv` is installed |
| `401 Unauthorized` from watsonx.ai | API key is expired, incorrect, or the key does not have access to the specified project | Regenerate the API key in IBM Cloud → Manage → API keys; verify `WATSONX_PROJECT_ID` matches the project |
| `ModuleNotFoundError: No module named 'xgboost'` | Virtual environment is not active or `requirements.txt` install failed | Run `source .venv/bin/activate` (macOS/Linux) or `.\.venv\Scripts\Activate.ps1` (Windows), then `pip install -r requirements.txt` again |
| `streamlit: command not found` | Streamlit not installed or virtual environment not active | Activate the virtual environment and confirm `streamlit` appears in `pip list` |
| Dashboard loads but ranked table is empty | Feature engineering or model training was not completed, or FastAPI is not running | Confirm steps 8–10 completed without errors; confirm FastAPI is reachable at `http://127.0.0.1:8000/health` |
| `Validation AUC: 0.5X` after training | Random seed produced a poor train/test split on the synthetic data | Re-run `python src/pipeline/generate_data.py` followed by `python src/ml/train.py` |

---

## Full Command Reference (in order)

```bash
# Clone and enter repo
git clone https://github.com/your-org/bob-ai-hackathon-maverick.git
cd bob-ai-hackathon-maverick

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .\.venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure credentials
cp src/.env.example src/.env
# Edit src/.env and fill in all variables

# Run schema (requires psql)
psql "$NEON_DATABASE_URL" -f src/etl/schema.sql

# Pipeline (run in order)
python src/data_generation/generate_fake_data.py
python src/data_generation/fetch_weather.py
python src/feature_engineering/build_features.py
python src/ml/train_model.py
python src/ml/predict.py

# Start services (two separate terminals)
cd src
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
streamlit run dashboard/app.py
```
