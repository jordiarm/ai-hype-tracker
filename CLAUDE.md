# AI Hype Tracker — Claude Context

## Project Summary

Batch data pipeline that tracks all GitHub event activity on AI repositories over 12 months (March 2025 – March 2026). Captures stars, pushes, pull requests, issues, and all other event types to measure developer engagement.

**Analytical question:** How has AI repository activity grown month-over-month in the last 12 months?

## Stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | Apache Airflow 2.9.3 | Self-hosted on GCE VM (`airflow-vm`) |
| Data Lake | Google Cloud Storage | Raw JSON + processed Parquet |
| Warehouse | BigQuery | Partitioned by `created_at`, clustered by `event_type` + `repo_name` |
| Transformation | dbt | Business logic, filtering, modeling |
| Dashboard | Looker Studio | Native BigQuery connector |
| Cloud Provider | GCP | Region: `europe-west4`, Location: `EU` |
| CI/CD | GitHub Actions | Lint + dbt build on push/PR |
| Linting | ruff, sqlfluff, terraform fmt | Python, SQL, Terraform |

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
├── .github/workflows/
│   └── ci.yml                                 # GitHub Actions CI pipeline
├── airflow/
│   ├── dags/
│   │   └── github_ingestion_daily_append.py   # Main ingestion DAG
│   └── keys/                                   # Service account keys (gitignored)
├── dbt/
│   ├── .sqlfluff                              # SQLFluff linting config
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_github_event_data.sql      # Cleans raw events, casts types
│   │   │   ├── schema.yml                     # Model documentation & tests
│   │   │   └── sources.yml                    # Source definitions (BigQuery)
│   │   ├── intermediate/
│   │   │   ├── int_ai_repo_names.sql          # AI repo identification (keywords + curated list)
│   │   │   ├── int_ai_events.sql              # Joins stg_github_event_data × int_ai_repo_names
│   │   │   ├── int_push_events.sql            # Filters stg events for PushEvent only
│   │   │   └── schema.yml                     # Model documentation & tests
│   │   └── marts/
│   │       ├── dim_ai_repos.sql               # Distinct AI repo names
│   │       ├── fct_ai_repo_events.sql         # Incremental fact table of all AI repo events
│   │       ├── schema.yml                     # Model documentation & tests
│   │       └── reporting/
│   │           ├── fct_daily_ai_repo_events.sql  # Daily aggregation by repo + event type
│   │           └── schema.yml
│   ├── dbt_project.yml
│   └── dbt_packages.yml
├── terraform/
│   ├── main.tf
│   └── variables.tf
├── .pre-commit-config.yaml                    # Pre-commit hooks (ruff, sqlfluff, terraform fmt)
├── .gitignore
├── Makefile                                   # Dev/deploy automation targets
├── docs/
└── README.md
```

## Airflow DAG

- **DAG ID:** `github_ingestion_daily_append`
- **Schedule:** `0 2 * * *` (2 AM UTC) with `catchup=True` (backfills from 2026-01-01)
- **Source:** `https://data.gharchive.org/YYYY-MM-DD-H.json.gz` (24 files/day)
- **Tasks:**
  1. `ingest_hour(hour, ds)` — (mapped × 24 via `task.expand()`) downloads a single hourly file, flattens JSON, uploads raw `.json.gz` + `.parquet` to GCS. Returns `{"hour", "rows", "corrupt_lines"}` via XCom. Note: `hour` must come before `ds` in the signature because Airflow injects context params (like `ds`) with defaults, and non-default args cannot follow default args.
  2. `load_to_bigquery` — validates ingest results, deletes existing data for the day, then loads Parquet from GCS into BigQuery (idempotent delete-then-append)
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
- **Materializations:** staging → view, intermediate → view, marts → table (reporting uses incremental)
- **Packages:** `dbt-labs/dbt_utils` 1.3.3
- **Source:** `raw.raw_github_events` (defined in `sources.yml`, references BigQuery dataset `ai_hype_tracker`)

### Current dbt model status

| Layer | Model | Status |
| --- | --- | --- |
| Staging | `stg_github_event_data` | Implemented — cleans raw events, casts types, filters null IDs |
| Intermediate | `int_ai_repo_names` | Implemented — identifies AI repos via keywords + curated list |
| Intermediate | `int_ai_events` | Implemented — joins `stg_github_event_data` × `int_ai_repo_names` (all event types) |
| Intermediate | `int_push_events` | Implemented — filters `stg_github_event_data` for PushEvent only |
| Marts | `dim_ai_repos` | Implemented — distinct AI repo names from `int_ai_repo_names` |
| Marts | `fct_ai_repo_events` | Implemented — incremental fact table from `int_ai_events`, deduped via `qualify row_number()`, uses `created_at` with 1-day lookback |
| Reporting | `fct_daily_ai_repo_events` | Implemented — incremental daily aggregation by repo + event type with month/year extraction, 1-day lookback window |

### dbt DAG

```text
stg_github_event_data ─→ int_ai_events ─→ fct_ai_repo_events ─→ fct_daily_ai_repo_events
                       ├→ int_ai_repo_names ┘   dim_ai_repos ←┘
                       └→ int_push_events
```

## AI Repo Identification (done in dbt, NOT in Airflow)

Airflow ingests all events raw. Filtering happens exclusively in dbt intermediate layer (`int_ai_repo_names` + `int_ai_events`).

**Keyword filter** (applied to `repo_name` in `int_ai_repo_names`):
`llm`, `gpt`, `ai`, `ml`, `neural`, `diffusion`, `langchain`, `ollama`, `embedding`, `transformer`

**Curated list** (always included):
`huggingface/transformers`, `langchain-ai/langchain`, `openai/openai-python`, `ollama/ollama`, `pytorch/pytorch`, `tensorflow/tensorflow`, `microsoft/autogen`, `ggerganov/llama.cpp`, `comfyanonymous/comfyui`, `nomic-ai/gpt4all`, plus several others. (All lowercased to match staging layer.)

## Key Design Decisions

- **No business logic in Airflow** — ingestion is generic; all filtering/classification is in dbt
- **Per-hour task granularity** — each hour is an independent Airflow task via `task.expand()`; individual retries, better observability
- **Idempotent BigQuery loads** — delete-then-append per partition day; safe to retry without duplicates
- **Deduplication in dbt** — `fct_ai_repo_events` uses `qualify row_number() over (partition by event_id)` to handle upstream duplicates
- **Batch over streaming** — MoM analysis doesn't need real-time; batch is simpler and cheaper
- **Self-hosted Airflow on GCE** — Cloud Composer is too expensive for a personal project
- **All event types tracked** — stars, pushes, PRs, issues, etc. give a fuller picture of developer engagement
- **Always filter on `created_at`** in BigQuery queries to use partitioning and control costs

## CI/CD (GitHub Actions)

Workflow at `.github/workflows/ci.yml`, triggered on push and PR to `main`.

**Jobs:**
1. **python-lint** — `ruff check` on `airflow/` code
2. **sql-lint** — `sqlfluff lint` on dbt models (BigQuery dialect)
3. **terraform-validate** — `terraform fmt -check` + `terraform validate`
4. **dbt-build-test** — `dbt deps` + `dbt build` against BigQuery (uses `ci` target)
5. **deploy-dag** — deploys DAG to Airflow VM (only on push to `main`, requires `production` environment approval)

**Required secret:** `GCP_SA_KEY` — base64-encoded GCP service account JSON key

## Makefile

Common development commands via `make`:

| Target | Description |
|---|---|
| `lint` | Runs `lint-python`, `lint-sql`, `lint-terraform` |
| `dbt-build` | `dbt deps` + `dbt build` in `dbt/` directory |
| `dbt-run`, `dbt-test`, `dbt-docs` | Individual dbt commands |
| `dbt-clean` | `dbt clean` in `dbt/` directory |
| `deploy-dag` | SCP DAG to VM via IAP |
| `deploy-key` | SCP service account key to VM via IAP |
| `deploy` | Full deploy (`deploy-dag` + `deploy-key`) |
| `ssh` | SSH into `airflow-vm` via IAP |
| `terraform-plan` | `terraform plan` |
| `terraform-destroy` | `terraform destroy` |
| `infra` | `terraform-init` + `terraform-apply` |
| `setup` | `infra` + `dbt-deps` + `setup-hooks` |
| `setup-hooks` | `pre-commit install` |
| `ci` | `lint` + `dbt-build` (local CI check) |

## Pre-commit Hooks

Config at `.pre-commit-config.yaml`. Runs on `git commit`:

- **ruff** (v0.11.4) — lints `airflow/` Python files
- **sqlfluff-lint** (v3.3.1) — lints `dbt/models/` SQL files (uses `dbt/.sqlfluff` config)
- **terraform_fmt** (v1.97.0) — formats Terraform files

Install with `make setup-hooks` or `pre-commit install`.

## SQLFluff Configuration

Config at `dbt/.sqlfluff`:

- Dialect: BigQuery, templater: jinja
- Max line length: 120, indent: 4 spaces
- Keywords and functions: lowercase
- Excluded rules: `ST06` (select wildcards), `RF02` (qualified references)

## Infrastructure Notes

- GCS lifecycle rule: abort incomplete multipart uploads after 1 day
- Terraform provisions: GCS bucket, BigQuery dataset, GCE VM, firewall rule (SSH via IAP only)
- Terraform remote state stored in GCS bucket `ai-hype-tracker-tf-state`
- Firewall allows SSH only from IAP CIDR `35.235.240.0/20`
- Airflow installed in virtualenv at `/opt/airflow` on the VM
