# GRID GUARD — Power Outage Prediction & Grid Equipment Failure Advisor

> **Bobathon 2026 · Track: AI · Use Case: U1**  
> **Team Maverick** — Heet Dadhaniya, Axit Dudhat, Aryan Jivani, Parth Vora

---

## The Problem

Utilities run on calendar-based maintenance schedules, ignoring condition signals already streaming from sensors into SCADA historians. Aging infrastructure, extreme weather events, and growing renewable loads make the status quo increasingly dangerous.

Signals like **temperature, vibration, and partial discharge** are available but unread — leading to unexpected, costly failures:

- Degrading and healthy transformers receive **identical treatment** under fixed schedules.
- Telemetry streams into SCADA historians where it remains **unread and unsynthesised**.
- Unexpected critical asset failure costs utilities **$1M+ per hour** in lost revenue, emergency labour, and regulatory fines.

---

## The Solution

Grid Guard is a four-stage pipeline that turns raw sensor telemetry into field-ready maintenance actions.

| Stage | Name | What it does | Technology |
|-------|------|--------------|------------|
| 01 | **Fuse** | Joins sensor telemetry, weather forecasts, and historical incident records in a single pipeline | Neon Postgres |
| 02 | **Predict** | Rolling feature window feeds a classifier to output failure probability per asset | XGBoost + SHAP |
| 03 | **Rank** | Assets scored by grid-impact severity: `probability × customers served × criticality tier` | Severity Engine |
| 04 | **Act** | Synthesises ranked data into a prioritised, plain-English maintenance and dispatch plan | IBM Bob / watsonx.ai |

---

## Architecture

```
Data Ingestion  →  ML Engine  →  Operational Logic  →  Interface
  Neon Postgres    XGBoost        Severity Ranker       Streamlit Dashboard
                   Scoring                              (Risk map, ranked table,
                                                         maintenance plan)
                              API Layer (FastAPI)
                              AI Synthesis (IBM Bob / watsonx)
```

A single FastAPI call updates all operator views in real-time. IBM Bob generates plain-English maintenance and crew plans from structured risk data.

---

## How IBM Bob Works in the Pipeline

**Input — Structured Risk Data:**

```json
{
  "asset_id": "TX-4092",
  "failure_prob": 0.84,
  "severity_score": 9.2,
  "top_shap_features": ["oil_temp_rise", "partial_discharge_count"],
  "weather_context": "Severe Storm Warning",
  "impact": "1,200 customers"
}
```

**Output — IBM Bob Field Briefing:**

> **PRIORITY ALPHA: Immediate dispatch to Transformer TX-4092.**
>
> Model flags 84% failure probability driven by critical oil temperature rise and partial discharge spikes. Combined with the 48-hour severe storm warning, this asset poses a high risk to 1,200 customers.
>
> **ACTION:** Deploy crew for immediate thermal inspection and oil sampling before storm onset.

---

## Severity Ranking Engine

Probability alone does not determine priority. The ranking engine applies:

```
Severity Score = P(Failure) × Customers Served × Tier Criticality
```

A **40% failure probability on a backbone transmission asset** outranks a **70% probability on a low-impact feeder**.

| | Low Probability | High Probability |
|---|---|---|
| **High Impact** | Preventative | ⚠️ **Critical Action** |
| **Low Impact** | Monitor | Medium Priority |

---

## Roadmap

### Near-Term — Integration
- Swap synthetic data for real utility SCADA feeds.
- Connect live NOAA/NWS severe-weather alerts.
- Zero structural changes required to the model architecture.

### Medium-Term — Optimisation
- Retrain on utility-specific historical incident records.
- Tune models to local fleet and operating environments.
- Refine severity weights based on operational feedback.

### At Scale — Grid Impact
- Reduce emergency maintenance costs by flagging outages weeks in advance.
- Improve SAIDI/SAIFI reliability metrics.
- Enable higher renewable utilisation within safe limits.

---

## Team

| Name | Role |
|------|------|
| Heet Dadhaniya | Team Maverick |
| Axit Dudhat | Team Maverick |
| Aryan Jivani | Team Maverick |
| Parth Vora | Team Maverick |

---

*Bobathon 2026 · Track: AI · Use Case: U1*
