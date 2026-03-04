from __future__ import annotations

import gzip
import io
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from airflow.decorators import dag, task
from google.cloud import bigquery, storage

PROJECT = "ai-hype-tracker"
BUCKET = "ai_hype_tracker_bucket"
BQ_DATASET = "ai_hype_tracker"
BQ_TABLE = "raw_github_events"
KEY_PATH = "/home/jordiarmentia/airflow/keys/airflow_service_account.json"



def _flatten_events(raw: list[dict]) -> list[dict]:
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for event in raw:
        rows.append({
            "event_id": event.get("id"),
            "event_type": event.get("type"),
            "actor_login": (event.get("actor") or {}).get("login"),
            "repo_name": (event.get("repo") or {}).get("name"),
            "created_at": event.get("created_at"),
            "ingested_at": ingested_at,
        })
    return rows


@dag(
    dag_id="github_ingestion_daily_append",
    start_date=datetime(2025, 3, 1),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["ingestion"],
)
def github_archive_ingestion():

    @task()
    def ingest_day(ds: str):
        """Download 24 hourly files for `ds`, flatten, upload raw JSON + per-hour Parquet to GCS."""
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
        gcs = storage.Client(project=PROJECT)
        bucket = gcs.bucket(BUCKET)

        year, month, day = ds.split("-")
        total_rows = 0

        for hour in range(24):
            url = f"https://data.gharchive.org/{ds}-{hour}.json.gz"
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"Skipping {url}: {e}")
                continue

            raw_bytes = resp.content

            # Upload raw JSON.gz to GCS
            raw_blob = bucket.blob(f"raw/{year}/{month}/{day}/{ds}-{hour}.json.gz")
            raw_blob.upload_from_string(raw_bytes, content_type="application/gzip")

            # Parse and flatten this hour only
            events = []
            with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            rows = _flatten_events(events)
            print(f"Hour {hour}: {len(events)} events")
            total_rows += len(rows)

            if not rows:
                del raw_bytes, events, rows
                continue

            # Write this hour's Parquet immediately — do not accumulate
            df = pd.DataFrame(rows)
            df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
            df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True)

            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                df.to_parquet(tmp_path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
                parquet_blob = bucket.blob(f"processed/{year}/{month}/{day}/events-{hour:02d}.parquet")
                parquet_blob.upload_from_filename(tmp_path)
            finally:
                os.unlink(tmp_path)

            del df, rows, events, raw_bytes

        if total_rows == 0:
            print("No rows collected for this day.")
            return

        print(f"Uploaded {total_rows} rows as Parquet for {ds}")

    @task()
    def load_to_bigquery(ds: str):
        """Load the day's Parquet from GCS into BigQuery."""
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
        year, month, day = ds.split("-")
        bq = bigquery.Client(project=PROJECT)

        uri = f"gs://{BUCKET}/processed/{year}/{month}/{day}/events-*.parquet"
        table_ref = f"{PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema=[
                bigquery.SchemaField("event_id", "STRING"),
                bigquery.SchemaField("event_type", "STRING"),
                bigquery.SchemaField("actor_login", "STRING"),
                bigquery.SchemaField("repo_name", "STRING"),
                bigquery.SchemaField("created_at", "TIMESTAMP"),
                bigquery.SchemaField("ingested_at", "TIMESTAMP"),
            ],
            time_partitioning=bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="created_at",
            ),
            clustering_fields=["event_type", "repo_name"],
        )

        load_job = bq.load_table_from_uri(uri, table_ref, job_config=job_config)
        load_job.result()
        print(f"Loaded {load_job.output_rows} rows into {table_ref}")

    ingest = ingest_day()
    load = load_to_bigquery()
    ingest >> load


github_archive_ingestion()
