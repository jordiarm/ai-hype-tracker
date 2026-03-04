variable "project" {
  description = "My project name"
  default     = "ai-hype-tracker"
}

variable "region" {
  description = "Project Region"
  default     = "europe-west4"
}

variable "location" {
  description = "Project Location"
  default     = "EU"
}

variable "bcs_bucket_name" {
  description = "My Storage Bucket Name"
  default     = "ai_hype_tracker_bucket"
}

variable "bq_dataset_name" {
  description = "My BigQuery Dataset Name"
  default     = "ai_hype_tracker"
}

variable "delete_contents_on_destroy" {
  default = true
}

variable "credentials" {
    description = "My credentials"
    default = "keys/terraform.json"
}

variable "vm_name" {
  description = "Airflow GCE VM name"
  default     = "airflow-vm"
}

variable "vm_machine_type" {
  description = "GCE machine type for Airflow VM"
  default     = "e2-medium"
}

variable "vm_zone" {
  description = "GCE VM zone"
  default     = "europe-west4-a"
}