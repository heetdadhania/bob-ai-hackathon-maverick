# Pitch Deck Outline — Grid Guard
**Team Maverick · Bobathon · Track: AI · Use Case: U1**

*5-minute live pitch. Each slide is a talking point, not a document.*

---

## Slide 1 — Title

- **Grid Guard: Power Outage Prediction & Grid Equipment Failure Advisor**
- Team Maverick — Heet Dadhaniya, Axit Dudhat, Aryan Jivani, Parth Vora
- Track: AI · Use Case: U1

---

## Slide 2 — Problem

- Utilities run on calendar-based maintenance — every asset gets serviced on a fixed
  schedule regardless of its actual condition. A transformer degrading under a heat
  wave and a healthy one get treated identically.
- The signals are already there: temperature, vibration, partial discharge, oil
  quality — streaming from sensors into SCADA historians where nobody reads them.
- When a critical asset fails unexpectedly, the cost runs **$1M+ per hour** in lost
  revenue, emergency labour, and regulatory exposure — for a failure that was
  predictable days in advance.
- Aging infrastructure + more frequent extreme weather + growing renewable load =
  the status quo is getting more dangerous, not less.

---

## Slide 3 — Solution

- **Stage 1 — Fuse:** Sensor telemetry, Open-Meteo weather forecasts, and historical
  incident records are joined in a single Neon Postgres pipeline — three data sources
  that utilities have but have never combined.
- **Stage 2 — Predict:** A rolling feature window feeds an XGBoost classifier that
  outputs a failure probability per asset, with SHAP values explaining *why* each
  asset was flagged.
- **Stage 3 — Rank:** Assets are scored by grid-impact severity
  (probability × customers served × criticality tier) — so crews go where the
  *consequences* are greatest, not just where failure is most likely.
- **Stage 4 — Act:** IBM Bob turns the ranked list into a prioritised,
  plain-English maintenance and crew dispatch plan — from raw data to field-ready
  orders in one automated workflow.

---

## Slide 4 — Demo / Architecture

- The full pipeline runs end-to-end: data generation → Neon Postgres → feature
  engineering → XGBoost scoring → severity ranking → Bob plan → FastAPI → Streamlit.
- **Key callout:** the severity ranker is the bridge between ML output and operational
  reality — a 40 % failure probability on a backbone transmission asset outranks a
  70 % probability on a low-impact feeder.
- The Streamlit dashboard gives operators three views in one screen: asset risk map,
  ranked table with SHAP context, and the generated maintenance plan — all updated
  from a single API call.

---

## Slide 5 — IBM Technology Integration

- **Bob / watsonx.ai is used at exactly one step: plan generation.** It is not used
  for data ingestion, feature engineering, or model scoring — deterministic code
  handles those because deterministic code is faster, cheaper, and auditable.
- The input to Bob is structured: a ranked list of assets with their severity scores,
  top SHAP-identified sensor readings, and 48-hour weather context. Bob's job is to
  synthesise that structured data into a plain-English field briefing.
- This is the step where a language model genuinely earns its place. A ranked table
  of risk scores requires an analyst to interpret; a written plan that names assets,
  states the basis for priority, and specifies the action does not. It goes directly
  into a crew briefing.
- Without Bob, the pipeline terminates at a spreadsheet. With Bob, it terminates at
  a decision.

---

## Slide 6 — Impact

- **Near-term:** swap synthetic sensor data for real utility SCADA feeds and
  connect live NOAA/NWS severe-weather alerts — the pipeline schema and model
  architecture support both with no structural changes.
- **Medium-term:** retrain on a utility's own historical incident record to produce
  asset-specific failure models tuned to their fleet, geography, and operating
  environment.
- **At scale:** a single Grid Guard deployment covering a regional grid could flag
  preventable outages weeks in advance, reducing emergency maintenance costs,
  improving SAIDI/SAIFI reliability metrics, and supporting cleaner grid operation
  by enabling higher renewable utilisation within safe asset limits.
- The core insight — fuse the data you already have, rank by consequence, generate
  a plan — applies to any utility, any grid size, anywhere in the world.
