-- Grid Guard — Neon Postgres schema
-- Run once against your Neon database before any other pipeline step.
-- All pipeline writes use ON CONFLICT DO NOTHING / DO UPDATE (idempotent).

-- ── Assets ───────────────────────────────────────────────────────────────────
-- One row per physical grid asset (transformer, switchgear, line segment).
CREATE TABLE IF NOT EXISTS assets (
    asset_id         TEXT             PRIMARY KEY,
    asset_type       TEXT             NOT NULL,  -- transformer | switchgear | line_segment
    region           TEXT             NOT NULL,
    lat              DOUBLE PRECISION NOT NULL,
    lon              DOUBLE PRECISION NOT NULL,
    install_year     INTEGER,
    customers_served INTEGER          NOT NULL DEFAULT 0,
    criticality_tier INTEGER          NOT NULL CHECK (criticality_tier BETWEEN 1 AND 3)
);

-- ── Sensor readings ──────────────────────────────────────────────────────────
-- Time-series readings from IoT sensors attached to each asset.
-- failed = 1 if the asset failed within 7 days of this reading (training label).
CREATE TABLE IF NOT EXISTS sensor_readings (
    id                   BIGSERIAL        PRIMARY KEY,
    asset_id             TEXT             NOT NULL
                             REFERENCES assets(asset_id) ON DELETE CASCADE,
    date                 DATE             NOT NULL,
    temperature          DOUBLE PRECISION,           -- °C
    vibration            DOUBLE PRECISION,           -- mm/s RMS
    oil_quality          DOUBLE PRECISION,           -- index 0–100, higher = better
    partial_discharge    DOUBLE PRECISION,           -- pC
    failed               SMALLINT         NOT NULL DEFAULT 0
                             CHECK (failed IN (0, 1)),
    UNIQUE (asset_id, date)
);

CREATE INDEX IF NOT EXISTS idx_sensor_asset_id
    ON sensor_readings (asset_id);

CREATE INDEX IF NOT EXISTS idx_sensor_date
    ON sensor_readings (date DESC);

-- ── Weather ──────────────────────────────────────────────────────────────────
-- Daily weather summaries keyed by region (joined to assets via assets.region).
CREATE TABLE IF NOT EXISTS weather (
    id                BIGSERIAL        PRIMARY KEY,
    region            TEXT             NOT NULL,
    date              DATE             NOT NULL,
    temperature_max   DOUBLE PRECISION,             -- °C
    precipitation_sum DOUBLE PRECISION,             -- mm
    windspeed_max     DOUBLE PRECISION,             -- km/h
    UNIQUE (region, date)
);

CREATE INDEX IF NOT EXISTS idx_weather_region
    ON weather (region);

CREATE INDEX IF NOT EXISTS idx_weather_date
    ON weather (date DESC);

-- ── Incidents ────────────────────────────────────────────────────────────────
-- Historical outage / failure events recorded against an asset.
CREATE TABLE IF NOT EXISTS incidents (
    incident_id        TEXT             PRIMARY KEY,
    asset_id           TEXT             NOT NULL
                           REFERENCES assets(asset_id) ON DELETE CASCADE,
    date               DATE             NOT NULL,
    cause              TEXT,                         -- e.g. overload | storm | age
    duration_hours     NUMERIC(8, 2),                -- outage duration in hours
    customers_affected INTEGER          NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_incidents_asset_id
    ON incidents (asset_id);

CREATE INDEX IF NOT EXISTS idx_incidents_date
    ON incidents (date DESC);

-- ── Feature matrix ───────────────────────────────────────────────────────────
-- Computed by feature_engineering/build_features.py; one row per asset.
CREATE TABLE IF NOT EXISTS feature_matrix (
    asset_id                  TEXT             PRIMARY KEY
                                  REFERENCES assets(asset_id) ON DELETE CASCADE,
    computed_at               TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    -- Rolling sensor stats (24 h window)
    temp_max_24h              DOUBLE PRECISION,
    temp_mean_24h             DOUBLE PRECISION,
    temp_delta_per_hour       DOUBLE PRECISION,
    vibration_max_24h         DOUBLE PRECISION,
    vibration_mean_24h        DOUBLE PRECISION,
    vibration_delta_per_hour  DOUBLE PRECISION,
    pd_max_24h                DOUBLE PRECISION,
    oil_quality_min_24h       DOUBLE PRECISION,

    -- Rolling sensor stats (72 h window)
    temp_max_72h              DOUBLE PRECISION,
    vibration_max_72h         DOUBLE PRECISION,

    -- Baseline deviations (z-score vs 30-day rolling mean)
    temp_zscore_30d           DOUBLE PRECISION,
    vibration_zscore_30d      DOUBLE PRECISION,

    -- Weather context (48 h ahead)
    forecast_temp_max_48h     DOUBLE PRECISION,
    forecast_wind_max_48h     DOUBLE PRECISION,

    -- Incident history
    days_since_last_incident  DOUBLE PRECISION,
    incident_count_90d        INTEGER,

    -- Asset metadata (denormalised for model convenience)
    criticality_tier          INTEGER,
    customers_served          INTEGER,
    asset_age_years           INTEGER,

    -- Ground-truth label (1 = failed within 7 days; NULL at inference time)
    label                     SMALLINT
);

-- ── Risk scores ──────────────────────────────────────────────────────────────
-- Written by ml/predict.py after each inference run.
CREATE TABLE IF NOT EXISTS risk_scores (
    asset_id             TEXT             PRIMARY KEY
                             REFERENCES assets(asset_id) ON DELETE CASCADE,
    scored_at            TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    failure_probability  DOUBLE PRECISION NOT NULL,
    severity_score       DOUBLE PRECISION NOT NULL,
    top_features         JSONB,           -- [{feature, shap_value}, ...]
    rank                 INTEGER
);
