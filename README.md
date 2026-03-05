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
| CI/CD | GitHub Actions | Lint + dbt build on push/PR |
| Linting | ruff, sqlfluff, terraform fmt | Python, SQL, Terraform |

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

## How to Reproduce

### Prerequisites

- A [Google Cloud Platform](https://cloud.google.com/) account with billing enabled
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- Python 3.10+
- [dbt-core](https://docs.getdbt.com/docs/core/installation) and `dbt-bigquery`

### 1. GCP Project Setup

```bash
# Create a GCP project (or use an existing one)
gcloud projects create ai-hype-tracker --name="AI Hype Tracker"
gcloud config set project ai-hype-tracker

# Enable required APIs
gcloud services enable compute.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable storage.googleapis.com

# Create a service account for Terraform
gcloud iam service-accounts create terraform \
  --display-name="Terraform"

# Grant Editor role (or use scoped roles: Storage Admin, BigQuery Admin, Compute Admin)
gcloud projects add-iam-policy-binding ai-hype-tracker \
  --member="serviceAccount:terraform@ai-hype-tracker.iam.gserviceaccount.com" \
  --role="roles/editor"

# Download the key
gcloud iam service-accounts keys create terraform/keys/terraform.json \
  --iam-account=terraform@ai-hype-tracker.iam.gserviceaccount.com

# Create a service account for Airflow (needs GCS + BigQuery access)
gcloud iam service-accounts create airflow \
  --display-name="Airflow"

gcloud projects add-iam-policy-binding ai-hype-tracker \
  --member="serviceAccount:airflow@ai-hype-tracker.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding ai-hype-tracker \
  --member="serviceAccount:airflow@ai-hype-tracker.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ai-hype-tracker \
  --member="serviceAccount:airflow@ai-hype-tracker.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Download the Airflow key
gcloud iam service-accounts keys create airflow_service_account.json \
  --iam-account=airflow@ai-hype-tracker.iam.gserviceaccount.com
```

### 2. Provision Infrastructure with Terraform

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

This creates:

- **GCS bucket** (`ai_hype_tracker_bucket`) — data lake for raw JSON and Parquet files
- **BigQuery dataset** (`ai_hype_tracker`) — data warehouse
- **GCE VM** (`airflow-vm`) — e2-medium running Ubuntu 22.04 with Airflow pre-installed
- **Firewall rule** — SSH via IAP only (secure access)

### 3. Deploy Airflow on the VM

```bash
# SSH into the VM via IAP
gcloud compute ssh airflow-vm --zone europe-west4-a --tunnel-through-iap

# The Terraform startup script already installed Airflow at /opt/airflow
# Activate the virtualenv
source /opt/airflow/bin/activate

# Install Python dependencies for the DAG
pip install pandas requests google-cloud-storage google-cloud-bigquery

# Create directories for the DAG and keys
mkdir -p ~/airflow/keys
mkdir -p /opt/airflow/dags
```

Copy files from your local machine to the VM (run from your local machine):

```bash
# Copy the DAG
gcloud compute scp airflow/dags/github_ingestion_daily_append.py \
  airflow-vm:/opt/airflow/dags/ \
  --zone europe-west4-a --tunnel-through-iap

# Copy the Airflow service account key
gcloud compute scp airflow_service_account.json \
  airflow-vm:~/airflow/keys/airflow_service_account.json \
  --zone europe-west4-a --tunnel-through-iap
```

Start Airflow (back on the VM):

```bash
source /opt/airflow/bin/activate
export AIRFLOW_HOME=/opt/airflow

# Create an admin user
airflow users create \
  --username admin --password admin \
  --firstname Admin --lastname User \
  --role Admin --email admin@example.com

# Start webserver and scheduler (in separate terminals or using nohup)
airflow webserver -p 8080 &
airflow scheduler &
```

The DAG `github_ingestion_daily_append` will appear in the Airflow UI. It backfills automatically from 2025-03-01 once unpaused.

### 4. Run dbt Transformations

```bash
# Install dbt (locally, not on the VM)
pip install dbt-core dbt-bigquery

# Create a dbt profile at ~/.dbt/profiles.yml
mkdir -p ~/.dbt
cat > ~/.dbt/profiles.yml << 'EOF'
ai_hype_tracker:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: service-account
      project: ai-hype-tracker
      dataset: ai_hype_tracker
      location: EU
      keyfile: /absolute/path/to/your/service-account-key.json  # update this path
      threads: 4
EOF

# Install dbt packages and run all models + tests
cd dbt
dbt deps
dbt build
```

This creates the full model chain: staging views → intermediate views → mart tables → reporting incremental tables.

### 5. Build the Dashboard

1. Open [Looker Studio](https://lookerstudio.google.com/)
2. Create a new report and add a **BigQuery** data source
3. Select project `ai-hype-tracker` → dataset `ai_hype_tracker` → table `fct_daily_ai_repo_events`
4. Create at least two tiles:
   - **Bar chart** — event count by `event_type` (categorical distribution)
   - **Time series** — total events per `event_month` (temporal trend)

---

## Makefile

A `Makefile` wraps common commands for convenience:

| Command | Description |
|---|---|
| `make terraform-init` | Initialize Terraform |
| `make terraform-plan` | Plan Terraform changes |
| `make terraform-apply` | Provision GCP infrastructure |
| `make terraform-destroy` | Destroy GCP infrastructure |
| `make dbt-build` | Install dbt packages, run models + tests |
| `make dbt-test` | Run dbt tests only |
| `make dbt-clean` | Clean dbt artifacts |
| `make dbt-docs` | Generate and serve dbt documentation |
| `make ssh` | SSH into the Airflow VM via IAP |
| `make deploy-dag` | Copy DAG to the VM |
| `make deploy-key` | Copy service account key to the VM |
| `make deploy` | Full deploy (DAG + key) |
| `make setup` | Full initial setup (infra + dbt deps + hooks) |
| `make setup-hooks` | Install pre-commit hooks |
| `make lint` | Run all linters (Python, SQL, Terraform) |
| `make ci` | Run linters + dbt build |

Run `make` followed by any target name. See the [Makefile](Makefile) for all available targets.

---

## CI/CD

A GitHub Actions workflow ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on every push and PR to `main`:

| Job | What it does |
|---|---|
| **Python Lint** | Checks Airflow DAG code with [ruff](https://docs.astral.sh/ruff/) |
| **SQL Lint** | Lints dbt models with [sqlfluff](https://sqlfluff.com/) (BigQuery dialect) |
| **Terraform Validate** | Runs `terraform fmt -check` and `terraform validate` |
| **dbt Build & Test** | Installs dbt packages, runs all models and tests against BigQuery |

### Setup: Add GCP credentials as a GitHub secret

The `dbt-build` job needs a GCP service account key to connect to BigQuery.

```bash
# Base64-encode your service account key
base64 -i /path/to/your/service-account-key.json | pbcopy

# Then in GitHub:
# 1. Go to your repo → Settings → Secrets and variables → Actions
# 2. Click "New repository secret"
# 3. Name: GCP_SA_KEY
# 4. Value: paste the base64-encoded key
```

The service account needs at minimum: `roles/bigquery.dataEditor` and `roles/bigquery.jobUser`.

---

## Pre-commit Hooks

The project uses [pre-commit](https://pre-commit.com/) to run linters on every commit:

| Hook | Version | Scope |
| --- | --- | --- |
| [ruff](https://docs.astral.sh/ruff/) | v0.11.4 | `airflow/` Python files |
| [sqlfluff](https://sqlfluff.com/) | v3.3.1 | `dbt/models/` SQL files |
| [terraform_fmt](https://github.com/antonbabenko/pre-commit-terraform) | v1.97.0 | Terraform files |

Install with `make setup-hooks` or `pre-commit install`.

---

## Timeframe

- **Start:** March 1, 2025
- **End:** March 2026
- **Granularity:** Hourly ingestion, daily batch processing, monthly aggregation for analysis
