terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "7.16.0"
    }
  }
}

provider "google" {
  credentials = file(var.credentials)
  project     = var.project
  region      = var.region
}

resource "google_storage_bucket" "gcs-bucket" {
  name          = var.bcs_bucket_name
  location      = var.location
  force_destroy = true

  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "AbortIncompleteMultipartUpload"
    }
  }
}

resource "google_bigquery_dataset" "example_dataset" {
  dataset_id                 = var.bq_dataset_name
  location                   = var.location
  delete_contents_on_destroy = var.delete_contents_on_destroy
}

resource "google_compute_instance" "airflow_vm" {
  name         = var.vm_name
  machine_type = var.vm_machine_type
  zone         = var.vm_zone

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 30
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    apt-get update -y
    apt-get install -y python3-pip python3-venv
    python3 -m venv /opt/airflow
    /opt/airflow/bin/pip install "apache-airflow==2.9.3" \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.10.txt"
    /opt/airflow/bin/airflow db init
  EOF

  tags = ["airflow"]
}

resource "google_compute_firewall" "airflow_firewall" {
  name    = "allow-airflow-iap"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP's fixed CIDR range — only allows SSH tunnelled through Google's IAP
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["airflow"]
}