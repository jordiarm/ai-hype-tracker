# ─── Configuration ────────────────────────────────────────────────────────────
GCP_PROJECT  := ai-hype-tracker
GCP_ZONE     := europe-west4-a
VM_NAME      := airflow-vm
DAG_SRC      := airflow/dags/github_ingestion_daily_append.py
DAG_DEST     := /opt/airflow/dags/
KEY_SRC      := airflow_service_account.json
KEY_DEST     := ~/airflow/keys/airflow_service_account.json
SCP_FLAGS    := --zone $(GCP_ZONE) --tunnel-through-iap

# ─── Terraform ────────────────────────────────────────────────────────────────
terraform-init:
	cd terraform && terraform init

terraform-plan:
	cd terraform && terraform plan

terraform-apply:
	cd terraform && terraform apply

terraform-destroy:
	cd terraform && terraform destroy

# ─── dbt ──────────────────────────────────────────────────────────────────────
dbt-deps:
	cd dbt && dbt deps

dbt-build: dbt-deps
	cd dbt && dbt build

dbt-run:
	cd dbt && dbt run

dbt-test:
	cd dbt && dbt test

dbt-clean:
	cd dbt && dbt clean

dbt-docs:
	cd dbt && dbt docs generate && dbt docs serve

# ─── VM Deployment ────────────────────────────────────────────────────────────
ssh:
	gcloud compute ssh $(VM_NAME) $(SCP_FLAGS)

deploy-dag:
	gcloud compute scp $(DAG_SRC) $(VM_NAME):$(DAG_DEST) $(SCP_FLAGS)

deploy-key:
	gcloud compute scp $(KEY_SRC) $(VM_NAME):$(KEY_DEST) $(SCP_FLAGS)

deploy: deploy-dag deploy-key

# ─── CI / Linting ─────────────────────────────────────────────────────────────
lint-python:
	ruff check airflow/

lint-sql:
	cd dbt && sqlfluff lint models/

lint-terraform:
	cd terraform && terraform fmt -check && terraform validate

lint: lint-python lint-sql lint-terraform

ci: lint dbt-build

# ─── Hooks ───────────────────────────────────────────────────────────────────
setup-hooks:
	pip3 install pre-commit
	pre-commit install

# ─── Composite ────────────────────────────────────────────────────────────────
infra: terraform-init terraform-apply

setup: infra dbt-deps setup-hooks

.PHONY: terraform-init terraform-plan terraform-apply terraform-destroy \
        dbt-deps dbt-build dbt-run dbt-test dbt-clean dbt-docs \
        ssh deploy-dag deploy-key deploy \
        lint-python lint-sql lint-terraform lint ci \
        setup-hooks infra setup
