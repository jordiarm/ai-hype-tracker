# GitHub AI Hype Tracker

## Project Summary

Batch data pipeline that tracks all GitHub event activity on AI repositories over 12 months (March 2025 – March 2026). Captures stars, pushes, pull requests, issues, and all other event types to measure developer engagement.

**Analytical Question:** How has AI repository activity grown month-over-month in the last 12 months?

---

## Stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | Apache Airflow 2.9.3 | Self-hosted on GCE VM |
| Data Lake | Google Cloud Storage | Raw JSON + processed Parquet |
| Warehouse | BigQuery | Partitioned by `created_at`, clustered by `event_type` + `repo_name` |
| Transformation | dbt | Business logic, filtering, modeling |
| Dashboard | Looker Studio | Native BigQuery connector |
| Cloud Provider | GCP | Region: `europe-west4` |

---

## Architecture Overview

```text
GitHub Archive (gharchive.org)
        │
        ▼
Airflow DAG (GCE VM)
  - Downloads 24 hourly JSON files per day
  - Flattens JSON to tabular format
  - Outputs per-hour Parquet files
        │
        ▼
GCS (Data Lake)
  - /raw/        → original .json.gz files
  - /processed/  → flattened Parquet files
        │
        ▼
BigQuery (Data Warehouse)
  - raw_github_events table (all event types)
  - Partitioned by created_at, clustered by event_type + repo_name
        │
        ▼
dbt (Transformations)
  - Staging: cleans and casts raw events
  - Intermediate: identifies AI repos (keywords + curated list), joins events
  - Marts: incremental fact tables, daily aggregations with month/year extraction
        │
        ▼
Looker Studio (Dashboard)
  - MoM activity growth across AI repos
  - Breakdown by event type (stars, pushes, PRs, issues)
  - Top repos by activity volume
```

---

## Repository Identification Strategy

AI repositories are identified exclusively in dbt (not in Airflow). Airflow ingests all events raw.

### Curated List (anchor repos — always included)

- `huggingface/transformers`
- `langchain-ai/langchain`
- `openai/openai-python`
- `ollama/ollama`
- `pytorch/pytorch`
- `tensorflow/tensorflow`
- `microsoft/autogen`
- `ggerganov/llama.cpp`
- `comfyanonymous/comfyui`
- `nomic-ai/gpt4all`

### Keyword Filter (applied to repo name)

Repos whose name contains any of the following terms are included:
`llm`, `gpt`, `ai`, `ml`, `neural`, `diffusion`, `langchain`, `ollama`, `embedding`, `transformer`

---

## Pipeline Design

### Ingestion (Airflow DAG)

- **DAG ID:** `github_ingestion_daily_append`
- **Schedule:** `0 2 * * *` (daily at 2 AM UTC) with `catchup=True` (backfills from 2025-03-01)
- **Source:** `https://data.gharchive.org/YYYY-MM-DD-H.json.gz` (24 files per day)
- **Tasks:**
  1. `ingest_day` — downloads hourly files, flattens JSON, uploads raw `.json.gz` + per-hour `.parquet` to GCS
  2. `load_to_bigquery` — loads Parquet files from GCS into BigQuery with `WRITE_APPEND`
- **Landing zones:**
  - Raw JSON: `gs://ai_hype_tracker_bucket/raw/YYYY/MM/DD/`
  - Processed Parquet: `gs://ai_hype_tracker_bucket/processed/YYYY/MM/DD/`

### BigQuery Schema (raw events table)

| Column | Type | Description |
|---|---|---|
| `event_id` | STRING | Unique event identifier |
| `event_type` | STRING | e.g. WatchEvent, PushEvent, IssuesEvent |
| `actor_login` | STRING | GitHub username |
| `repo_name` | STRING | org/repo format |
| `created_at` | TIMESTAMP | Event timestamp (partition key) |
| `ingested_at` | TIMESTAMP | Pipeline ingestion timestamp |

### dbt Models

```text
models/
├── staging/
│   └── stg_github_event_data.sql        # Cleans raw events, casts types, filters null IDs
├── intermediate/
│   ├── int_ai_repo_names.sql            # AI repo identification (keywords + curated list)
│   ├── int_ai_events.sql                # Joins stg events × AI repo names (all event types)
│   └── int_push_events.sql              # Filters stg events for PushEvent only
└── marts/
    ├── dim_ai_repos.sql                 # Distinct AI repo names
    ├── fct_ai_repo_events.sql           # Incremental fact table of all AI repo events
    └── reporting/
        └── fct_daily_ai_repo_events.sql # Daily aggregation by repo + event type (with month/year)
```

**dbt DAG:**

```text
stg_github_event_data ─→ int_ai_events ─→ fct_ai_repo_events ─→ fct_daily_ai_repo_events
                       ├→ int_ai_repo_names ┘   dim_ai_repos ←┘
                       └→ int_push_events
```

**Materializations:** staging → view, intermediate → view, marts → table (reporting uses incremental)

---

## Infrastructure

- **GCP Project:** `ai-hype-tracker`
- **GCE VM:** `airflow-vm`, `e2-medium`, zone `europe-west4-a`, Ubuntu 22.04 LTS
- **Airflow:** installed in virtualenv at `/opt/airflow` on the VM
- **Terraform:** provisions GCS bucket, BigQuery dataset, GCE VM, firewall rule (SSH via IAP only)
- **GCS lifecycle:** abort incomplete multipart uploads after 1 day

---

## Key Design Decisions

- **No business logic in Airflow** — ingestion is generic; all filtering/classification is in dbt
- **All event types tracked** — stars, pushes, PRs, issues give a fuller picture of developer engagement
- **Per-hour Parquet** — write each hour immediately to avoid memory accumulation on the VM
- **Batch over streaming** — MoM analysis doesn't need real-time; batch is simpler and cheaper
- **Self-hosted Airflow on GCE** — Cloud Composer is too expensive for a personal project
- **Always filter on `created_at`** in BigQuery queries to use partitioning and control costs

---

## Timeframe

- **Start:** March 1, 2025
- **End:** March 2026
- **Granularity:** Hourly ingestion, daily batch processing, monthly aggregation for analysis
