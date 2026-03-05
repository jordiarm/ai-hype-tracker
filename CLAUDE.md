# AI Hype Tracker — Claude Context

## Project Summary

Batch data pipeline that tracks AI repository star activity on GitHub over 12 months (March 2025 – March 2026). GitHub stars are used as a proxy for developer attention/hype.

**Analytical question:** How has AI repository star activity grown month-over-month in the last 12 months?

## Stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | Apache Airflow 2.9.3 | Self-hosted on GCE VM (`airflow-vm`) |
| Data Lake | Google Cloud Storage | Raw JSON + processed Parquet |
| Warehouse | BigQuery | Partitioned by `created_at`, clustered by `event_type` + `repo_name` |
| Transformation | dbt | Business logic, filtering, modeling |
| Dashboard | Looker Studio | Native BigQuery connector |
| Cloud Provider | GCP | Region: `europe-west4`, Location: `EU` |

## GCP Resources

- **Project ID:** `ai-hype-tracker`
- **GCS Bucket:** `ai_hype_tracker_bucket`
- **BigQuery Dataset:** `ai_hype_tracker`
- **BigQuery Table:** `raw_github_events`
- **GCE VM:** `airflow-vm`, `e2-medium`, zone `europe-west4-a`, Ubuntu 22.04 LTS
- **Terraform credentials:** `terraform/keys/terraform.json`
- **Airflow service account key:** `/home/jordiarmentia/airflow/keys/airflow_service_account.json` (on VM)

## Repository Structure

```
ai_hype_tracker/
├── airflow/
│   ├── dags/
│   │   └── github_ingestion_daily_append.py   # Main ingestion DAG
│   └── keys/                                   # Service account keys (gitignored)
├── dbt/
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_github_repo_data.sql       # Cleans raw events, casts types
│   │   │   ├── schema.yml                     # Model documentation & tests
│   │   │   └── sources.yml                    # Source definitions (BigQuery)
│   │   ├── intermediate/                      # Planned: int_star_events, int_ai_repos
│   │   └── marts/                             # Planned: fct_ai_repo_stars, agg_stars_by_month
│   ├── dbt_project.yml
│   └── dbt_packages.yml
├── terraform/
│   ├── main.tf
│   └── variables.tf
├── docs/
└── README.md
```

## Airflow DAG

- **DAG ID:** `github_ingestion_daily_append`
- **Schedule:** `0 2 * * *` (2 AM UTC) with `catchup=True` (backfills from 2025-03-01)
- **Source:** `https://data.gharchive.org/YYYY-MM-DD-H.json.gz` (24 files/day)
- **Tasks:**
  1. `ingest_day` — downloads 24 hourly files, flattens JSON, uploads raw `.json.gz` + per-hour `.parquet` to GCS
  2. `load_to_bigquery` — loads day's Parquet files from GCS into BigQuery with `WRITE_APPEND`
- **GCS paths:**
  - Raw JSON: `gs://ai_hype_tracker_bucket/raw/YYYY/MM/DD/{ds}-{H}.json.gz`
  - Processed Parquet: `gs://ai_hype_tracker_bucket/processed/YYYY/MM/DD/events-{HH}.parquet`

## BigQuery Schema (`raw_github_events`)

| Column | Type |
|---|---|
| `event_id` | STRING |
| `event_type` | STRING |
| `actor_login` | STRING |
| `repo_name` | STRING |
| `created_at` | TIMESTAMP (partition key) |
| `ingested_at` | TIMESTAMP |

## dbt Configuration

- **Profile:** `ai_hype_tracker`
- **Materializations:** staging → view, intermediate → view, marts → table
- **Packages:** `dbt-labs/dbt_utils` 1.3.3
- **Source:** `raw.raw_github_repos` (defined in `sources.yml`, references BigQuery dataset `ai_hype_tracker`)

### Current dbt model status

| Layer | Model | Status |
| --- | --- | --- |
| Staging | `stg_github_repo_data` | Implemented — cleans raw events, casts types, filters null IDs |
| Intermediate | `int_star_events` | Not yet implemented |
| Intermediate | `int_ai_repos` | Not yet implemented |
| Marts | `fct_ai_repo_stars` | Not yet implemented |
| Marts | `agg_stars_by_month` | Not yet implemented |

## AI Repo Identification (planned for dbt, NOT in Airflow)

Airflow ingests all events raw. Filtering will happen exclusively in dbt intermediate/marts layers (not yet implemented).

**Keyword filter** (to be applied to `repo_name`):
`llm`, `gpt`, `ai`, `ml`, `neural`, `diffusion`, `langchain`, `ollama`, `embedding`, `transformer`

**Curated list** (to be always included):
`huggingface/transformers`, `langchain-ai/langchain`, `openai/openai-python`, `ollama/ollama`, `pytorch/pytorch`, `tensorflow/tensorflow`, `microsoft/autogen`, `ggerganov/llama.cpp`, `comfyanonymous/ComfyUI`, `nomic-ai/gpt4all`, plus several others.

## Key Design Decisions

- **No business logic in Airflow** — ingestion is generic; all filtering/classification is in dbt
- **Per-hour Parquet** — write each hour immediately to avoid memory accumulation on the VM
- **Batch over streaming** — MoM analysis doesn't need real-time; batch is simpler and cheaper
- **Self-hosted Airflow on GCE** — Cloud Composer is too expensive for a personal project
- **Stars (`WatchEvent`) as hype proxy** — measures developer attention, not productivity
- **Always filter on `created_at`** in BigQuery queries to use partitioning and control costs

## Infrastructure Notes

- GCS lifecycle rule: abort incomplete multipart uploads after 1 day
- Terraform provisions: GCS bucket, BigQuery dataset, GCE VM, firewall rule (SSH via IAP only)
- Firewall allows SSH only from IAP CIDR `35.235.240.0/20`
- Airflow installed in virtualenv at `/opt/airflow` on the VM
