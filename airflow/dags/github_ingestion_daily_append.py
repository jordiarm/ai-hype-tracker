from __future__ import annotations

import gzip
import io
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta

import pandas as pd
import requests
from airflow.decorators import dag, task
from google.cloud import bigquery, storage

PROJECT = "ai-hype-tracker"
BUCKET = "ai_hype_tracker_bucket"
BQ_DATASET = "ai_hype_tracker"
BQ_TABLE = "raw_github_events"
KEY_PATH = "/home/jordiarmentia/airflow/keys/airflow_service_account.json"

REQUEST_TIMEOUT_SECONDS = 60
HOURS_PER_DAY = 24

logger = logging.getLogger(__name__)


@dag(
    dag_id="github_ingestion_daily_append",
    start_date=datetime(2025, 3, 1),
    schedule="0 2 * * *",
    catchup=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=60),
    },
    tags=["ingestion"],
)
def github_archive_ingestion():

    @task(execution_timeout=timedelta(minutes=15))
    def ingest_hour(ds: str, hour: int) -> dict:
        """Download a single hourly file for `ds`, flatten, upload raw JSON + Parquet to GCS.

        Returns a dict with row count and status for downstream validation.
        """
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
        gcs = storage.Client(project=PROJECT)
        bucket = gcs.bucket(BUCKET)

        year, month, day = ds.split("-")
        url = f"https://data.gharchive.org/{ds}-{hour}.json.gz"

        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to download %s: %s", url, e)
            raise

        raw_bytes = resp.content

        # Upload raw JSON.gz to GCS
        raw_blob = bucket.blob(f"raw/{year}/{month}/{day}/{ds}-{hour}.json.gz")
        raw_blob.upload_from_string(raw_bytes, content_type="application/gzip")

        # Use the DAG execution date as ingested_at for deterministic timestamps
        ingested_at = f"{ds}T{hour:02d}:00:00+00:00"
        rows = []
        hour_count = 0
        corrupt_lines = 0
        with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    corrupt_lines += 1
                    continue
                rows.append({
                    "event_id": event.get("id"),
                    "event_type": event.get("type"),
                    "actor_login": (event.get("actor") or {}).get("login"),
                    "repo_name": (event.get("repo") or {}).get("name"),
                    "created_at": event.get("created_at"),
                    "ingested_at": ingested_at,
                })
                hour_count += 1
        del raw_bytes

        if corrupt_lines > 0:
            logger.warning(
                "Hour %d: %d corrupt JSON lines skipped out of %d total",
                hour, corrupt_lines, hour_count + corrupt_lines,
            )

        logger.info("Hour %d: %d events extracted", hour, hour_count)

        if not rows:
            logger.warning("Hour %d: no events collected", hour)
            return {"hour": hour, "rows": 0, "corrupt_lines": corrupt_lines}

        # Write this hour's Parquet immediately
        df = pd.DataFrame(rows)
        del rows
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

        del df

        return {"hour": hour, "rows": hour_count, "corrupt_lines": corrupt_lines}

    @task(execution_timeout=timedelta(minutes=30))
    def load_to_bigquery(ds: str, ingest_results: list[dict]):
        """Load the day's Parquet from GCS into BigQuery.

        Uses WRITE_TRUNCATE to ensure idempotent loads — safe to retry
        without duplicating data. Validates ingest results before loading.
        """
        total_rows = sum(r["rows"] for r in ingest_results)
        failed_hours = [r["hour"] for r in ingest_results if r["rows"] == 0]

        if failed_hours:
            logger.warning("Hours with no data: %s", failed_hours)

        if total_rows == 0:
            logger.warning("No rows collected for %s — skipping BigQuery load", ds)
            return

        logger.info("Loading %d total rows for %s into BigQuery", total_rows, ds)

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH
        year, month, day = ds.split("-")
        bq = bigquery.Client(project=PROJECT)

        uri = f"gs://{BUCKET}/processed/{year}/{month}/{day}/events-*.parquet"
        table_ref = f"{PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

        # Delete existing data for this day first, then append.
        # This makes the load idempotent — retries won't duplicate rows.
        delete_query = f"""
            DELETE FROM `{table_ref}`
            WHERE DATE(created_at) = '{ds}'
        """
        bq.query(delete_query).result()
        logger.info("Deleted existing rows for %s from %s", ds, table_ref)

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
        load_job.result(timeout=3600)
        logger.info("Loaded %d rows into %s for %s", load_job.output_rows, table_ref, ds)

    hours = list(range(HOURS_PER_DAY))
    ingest_results = ingest_hour.expand(hour=hours)
    load_to_bigquery(ds="{{ ds }}", ingest_results=ingest_results)


github_archive_ingestion()
