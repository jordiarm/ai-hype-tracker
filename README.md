# GitHub AI Hype Tracker — Project Plan

## Project Summary

This project is a batch data pipeline that tracks and analyzes the growth of AI-related repository star activity on GitHub over the last 12 months (March 2025 – March 2026). The goal is to measure AI hype quantitatively by treating GitHub stars as a proxy for developer attention and interest.

The pipeline ingests hourly event data from [GitHub Archive](https://www.gharchive.org), filters for AI-related repositories using a combination of keyword matching and a curated list of known AI projects, and produces a month-over-month dashboard showing how star activity has evolved across the AI ecosystem.

**Analytical Question:** How has AI repository star activity grown month-over-month in the last 12 months?

---

## Stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | Apache Airflow | Self-hosted on a GCE VM |
| Data Lake | Google Cloud Storage (GCS) | Raw JSON + processed Parquet |
| Warehouse | BigQuery | Partitioned by date, clustered by repo |
| Transformation | dbt | Business logic, filtering, modeling |
| Dashboard | Looker Studio | Native BigQuery connector |
| Cloud Provider | GCP | |

---

## Repository Identification Strategy

AI repositories are identified using two complementary approaches applied in dbt:

### Curated List (anchor repos — always included)
- `openclaw/openclaw`
- `qwibitai/nanoclaw`
- `sipeed/picoclaw`
- `HKUDS/nanobot`
- `nearai/ironclaw`
- `huggingface/transformers`
- `langchain-ai/langchain`
- `openai/openai-python`
- `ollama/ollama`
- `pytorch/pytorch`
- `tensorflow/tensorflow`
- `microsoft/autogen`
- `ggerganov/llama.cpp`
- `comfyanonymous/ComfyUI`
- `nomic-ai/gpt4all`

### Keyword Filter (applied to repo name)
Repos whose name contains any of the following terms are included:
`llm`, `gpt`, `ai`, `ml`, `neural`, `diffusion`, `langchain`, `ollama`, `embedding`, `transformer`

> **Note:** Filtering happens exclusively in dbt. Airflow ingests all `WatchEvent` (star) data raw — no business logic at ingestion time.

---

## Architecture Overview

```
GitHub Archive (gharchive.org)
        │
        ▼
Airflow DAG (GCE VM)
  - Downloads hourly JSON files
  - Flattens JSON to tabular format using Python
  - Outputs Parquet files
        │
        ▼
GCS (Data Lake)
  - /raw/        → original JSON files
  - /processed/  → flattened Parquet files
        │
        ▼
BigQuery (Data Warehouse)
  - Raw events table (partitioned by date, clustered by event_type + repo_name)
        │
        ▼
dbt (Transformations)
  - Filters for WatchEvent (stars) only
  - Applies AI repo identification (curated list + keyword filter)
  - Builds month-over-month aggregation models
        │
        ▼
Looker Studio (Dashboard)
  - MoM star growth chart
  - Top AI repos by star velocity
  - Curated vs keyword-matched repo breakdown
```

---

## Pipeline Design

### Ingestion (Airflow DAG)

- **Schedule:** Daily batch (processes prior day's hourly files)
- **Source:** `https://data.gharchive.org/YYYY-MM-DD-H.json.gz` (24 files per day)
- **Event type filter:** Ingest all events initially; filter in dbt
- **Output format:** Parquet (columnar, efficient for BigQuery loading)
- **Landing zones:**
  - Raw JSON → `gs://<bucket>/raw/YYYY/MM/DD/`
  - Processed Parquet → `gs://<bucket>/processed/YYYY/MM/DD/`

### BigQuery Schema (raw events table)

| Column | Type | Description |
|---|---|---|
| `event_id` | STRING | Unique event identifier |
| `event_type` | STRING | e.g. WatchEvent, PushEvent |
| `actor_login` | STRING | GitHub username |
| `repo_name` | STRING | org/repo format |
| `created_at` | TIMESTAMP | Event timestamp |
| `ingested_at` | TIMESTAMP | Pipeline ingestion timestamp |

**Partitioning:** `created_at` (daily)
**Clustering:** `event_type`, `repo_name`

### dbt Models

```
models/
├── staging/
│   └── stg_github_events.sql        # Cleans raw events, casts types
├── intermediate/
│   ├── int_star_events.sql           # Filters WatchEvent only
│   └── int_ai_repos.sql              # Applies AI repo identification logic
└── marts/
    ├── fct_ai_repo_stars.sql         # Fact table: one row per star event on AI repo
    └── agg_stars_by_month.sql        # MoM aggregation for dashboard
```

### Dashboard (Looker Studio)

Key charts:
- **MoM star growth (line chart):** Total AI repo stars per month over 12 months
- **Top repos by star velocity (bar chart):** Which repos gained the most stars MoM
- **Curated vs discovered repos (pie/stacked):** Stars from curated list vs keyword-matched repos
- **Emerging repos (table):** Repos not in curated list that appear via keyword filter, ranked by stars

---

## Timeframe

- **Start:** March 1, 2025
- **End:** March 3, 2026 (today)
- **Granularity:** Hourly ingestion, daily batch processing, monthly aggregation for analysis

---

## Infrastructure Notes

- **Airflow:** Self-hosted on a small GCE VM (e2-medium or similar). Do NOT use Cloud Composer — too expensive for a personal project.
- **GCS:** Standard storage class is sufficient. Apply lifecycle rules to delete raw JSON after 30 days to control costs.
- **BigQuery:** Use partitioned tables to minimize query costs. Always filter on `created_at` partition column in queries.
- **Terraform:** Use Terraform to provision GCS bucket, BigQuery dataset, and GCE VM for reproducibility.

---

## Project Phases

### Phase 1 — Infrastructure Setup
- [ ] Provision GCP resources with Terraform (GCE VM, GCS bucket, BigQuery dataset)
- [ ] Install and configure Airflow on GCE VM
- [ ] Set up dbt project connected to BigQuery
- [ ] Validate connectivity across all layers

### Phase 2 — Ingestion Pipeline
- [ ] Build Airflow DAG for daily batch ingestion
- [ ] Implement Python JSON flattening logic
- [ ] Write Parquet output to GCS
- [ ] Load Parquet from GCS to BigQuery raw table
- [ ] Backfill 12 months of historical data (March 2025 – March 2026)

### Phase 3 — Transformations
- [ ] Build dbt staging model (`stg_github_events`)
- [ ] Build intermediate models (star filter, AI repo identification)
- [ ] Build fact table (`fct_ai_repo_stars`)
- [ ] Build MoM aggregation model (`agg_stars_by_month`)
- [ ] Add dbt tests (not null, unique, accepted values)

### Phase 4 — Dashboard
- [ ] Connect Looker Studio to BigQuery
- [ ] Build MoM growth chart
- [ ] Build top repos by star velocity chart
- [ ] Build curated vs discovered breakdown
- [ ] Build emerging repos table

### Phase 5 — Documentation & Submission
- [ ] Write README with architecture diagram
- [ ] Document pipeline design decisions
- [ ] Record short demo video (if required)
- [ ] Submit for peer review

---

## Key Design Decisions & Rationale

- **Batch over streaming:** MoM analysis does not require real-time data. Batch is simpler, cheaper, and sufficient.
- **Python for JSON flattening (not Spark):** GitHub Archive JSON is well-structured. Python handles flattening cleanly without the overhead of managing a Spark/Dataproc cluster.
- **dbt for business logic:** All filtering and repo identification logic lives in dbt, not in Airflow. This keeps ingestion generic and transformations transparent and testable.
- **Stars as hype proxy:** Stars measure developer attention and interest, not development activity. This is intentional — the project is explicitly tracking hype, not productivity.
- **Airflow over Kestra:** Chosen because of existing production familiarity, not because it is objectively superior for this use case.