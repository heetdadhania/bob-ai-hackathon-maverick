# Grid Guard — Source Code

This directory contains the full Grid Guard pipeline.

```
src/
├── .env.example              # Environment variable template — copy to .env
├── requirements.txt          # Python dependencies
├── data_generation/          # Synthetic asset/sensor/incident data + weather fetch
├── etl/                      # Schema, extract, transform, load to Neon Postgres
├── feature_engineering/      # Rolling feature computation
├── ml/                       # XGBoost training and inference
├── llm/                      # IBM Bob / watsonx.ai plan generation
├── api/                      # FastAPI server
└── dashboard/                # Streamlit operator dashboard
```

See [`docs/setup-guide.md`](../docs/setup-guide.md) for the full run order.

**Quick start (after configuring `.env`):**

```bash
python etl/schema.sql          # via psql or init_db helper — see setup guide
python data_generation/generate_fake_data.py
python data_generation/fetch_weather.py
python etl/extract.py && python etl/transform.py && python etl/load_to_neon.py
python feature_engineering/build_features.py
python ml/train_model.py
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
streamlit run dashboard/app.py
```
