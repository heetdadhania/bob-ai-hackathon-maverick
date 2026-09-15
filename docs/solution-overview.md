# Solution Overview: Grid Guard

## What Grid Guard Does in One Sentence

Grid Guard takes the sensor telemetry, weather forecasts, and incident history that
utilities already have — but have never connected — and turns them into a prioritised,
plain-English maintenance plan that a grid operator can act on before a failure occurs.

---

## The Core Pipeline

The system is a four-stage pipeline. Each stage has a clear responsibility, and the
output of each stage is the input to the next.

### Stage 1 — Data Fusion

Three data sources are ingested and joined in a single Neon Postgres instance:

- **Asset sensor telemetry** — temperature, vibration, partial discharge readings, and
  oil-quality metrics for each monitored asset.
- **Weather forecasts** — multi-day ahead forecasts from the Open-Meteo API, keyed to
  each asset's geographic location.
- **Historical incident records** — past outage events, their affected assets, and
  timestamps, used to label past conditions as failure or non-failure cases.

Combining these three sources is the foundational design decision. Most condition-
monitoring tools work on sensor data alone. Most outage post-mortems focus on incident
logs alone. Neither view is sufficient because failures are typically caused by the
*interaction* of equipment condition and operating stress — a transformer that would
survive the same heat event in year three of its life may fail in year twenty. Joining
all three sources in one place is the prerequisite for everything downstream.

### Stage 2 — Feature Engineering

Raw sensor readings and weather values are not fed directly to the model. A rolling
feature window computes summaries — recent maximums, rates of change, deviation from
historical baseline — that capture the *trajectory* of an asset's condition, not just
its current snapshot. An asset that has been trending toward its temperature limit
over the past 72 hours is a different risk profile from one that spiked briefly and
recovered, even if their current readings are identical. The feature engineering step
encodes that distinction.

### Stage 3 — Risk Scoring and Severity Ranking

An XGBoost classifier produces a failure probability score for each asset.
Probability alone is not enough to prioritise field work: a low-criticality asset
with a 70 % failure probability may matter far less than a transmission backbone
asset with a 40 % probability that, if it fails, takes 50,000 customers offline.

To address this, each asset is assigned a **grid-impact severity score**:

```
severity = failure_probability × customers_served × criticality_tier
```

This ranking surfaces the assets where acting has the highest consequence — not just
the assets most likely to fail. It is the difference between a risk list and a
resource allocation guide.

### Stage 4 — IBM Bob / watsonx.ai Plan Generation

The top-ranked assets and their risk context are passed to IBM Bob, running on
watsonx.ai. Bob generates a prioritised, plain-English maintenance and crew
pre-positioning plan. The output names specific assets, explains the basis for their
priority (e.g. elevated vibration trend + incoming temperature event), and recommends
crew actions — inspection, targeted replacement, pre-staged spares, or load
shedding — in the order field teams should act on them.

This is the step where natural language genuinely adds value. A ranked table of risk
scores requires interpretation; a plan written in plain English does not. Field crew
leads can read it, forward it, and act on it without needing to understand the model
mechanics behind it.

---

## What Makes This Different from Simpler Alternatives

**A calendar schedule** treats every asset as degrading at the same rate. It sends
crews to healthy equipment and ignores stressed equipment in between service dates.
Grid Guard replaces calendar time with condition-derived risk.

**Sensor-only anomaly detection** tells operators that something looks unusual, but
it does not tell them whether that anomaly matters. Without weather context, the same
temperature reading looks identical on a mild day and on the eve of a heat dome.
Without incident history, there is no way to know whether this anomaly pattern has
preceded failures before.

**A bare risk score** requires a human analyst to translate it into action. The more
assets in scope, the more analyst time that requires, and the more opportunity for
inconsistent or delayed decisions. The Bob-generated plan removes that translation
step entirely.

The combination of all three data sources, consequence-weighted ranking, and
natural-language plan output is what differentiates Grid Guard from each of these
partial approaches.

---

## Key Design Decisions

### XGBoost Over Deep Learning

The training dataset for this problem is tabular (a row per asset per time window)
and at the scale of a hackathon dataset — hundreds to low thousands of labelled
examples, not millions. XGBoost is the right model for this regime: it generalises
well on structured tabular data without requiring large sample sizes, training is fast
enough to re-run in the pipeline without a GPU, and it produces per-feature importance
scores natively through SHAP values. Deep learning would require significantly more
data to avoid overfitting and would produce a less interpretable result, which matters
for operator trust — no grid operator will act on a black-box score without some
explanation of *why*.

### Neon Postgres for the Data Layer

The team has four members working across multiple components simultaneously. A shared,
always-on Postgres instance eliminates the "works on my machine" problem for data: one
connection string, no local database setup, no sync conflicts between team members.
Neon's serverless model also means there is no running cost when the pipeline is idle,
which is appropriate for a hackathon. For a production deployment, the same Postgres
schema would transfer directly to any managed Postgres provider.

### IBM Bob / watsonx.ai for Plan Generation — Not for Everything

Bob is used specifically and only at the plan-generation step, where the input is
structured and the output genuinely needs to be natural language. It is not used for
data ingestion, feature engineering, or model scoring, where deterministic code is
faster, cheaper, and more auditable. This keeps the LLM in its highest-value role —
synthesising structured information into a human-ready communication — rather than
using it as a general-purpose component throughout the pipeline.

---

## The Operator Experience

A grid operator opens the Streamlit dashboard and sees three things:

1. **Asset risk map** — a geographic view of monitored assets colour-coded by current
   severity score. At a glance, the operator can see where risk is concentrating and
   whether it correlates with an incoming weather event.

2. **Ranked risk table** — the top assets sorted by severity score, with columns for
   failure probability, criticality tier, customers served, the key sensor reading
   driving the score, and the upcoming weather conditions relevant to each asset.
   The table is scannable in under a minute.

3. **Generated maintenance plan** — the Bob-generated plain-English plan, displayed
   alongside the table. It names assets in priority order, states the basis for each
   recommendation, and specifies the recommended action. The operator can copy it
   directly into a crew briefing or work-order system.

In day-to-day use, the intended workflow is a morning review — the operator checks the
dashboard as part of their shift startup, reviews any assets that have moved up the
risk ranking since the previous day, reads the generated plan, and either approves
the recommendations or adjusts crew assignments accordingly. The system is advisory,
not autonomous: the operator retains full decision authority and uses the dashboard to
be better informed, not to be replaced.

---

*For implementation specifics — data schema, model training pipeline, API design, and
deployment — see [`docs/architecture.md`](architecture.md).*
