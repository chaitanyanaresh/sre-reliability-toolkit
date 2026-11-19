variable "project_id" {
  type        = string
  description = "Google Cloud project ID to deploy into."
}

variable "region" {
  type        = string
  description = "Google Cloud region for the service and monitoring resources."
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  description = "Name of the Cloud Run service."
  default     = "checkout-api"
}

variable "container_image" {
  type        = string
  description = "Container image to deploy. Placeholder sample image by default; point this at your Artifact Registry image in real use."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "latency_threshold_ms" {
  type        = number
  description = "p95 latency alert threshold in milliseconds; mirrors the latency SLO threshold in ../slo/config.json."
  default     = 300
}

variable "notification_channels" {
  type        = list(string)
  description = "Cloud Monitoring notification channel IDs to notify on alerts (e.g. the on-call rotation's channel). Empty list = alerts visible in console only."
  default     = []
}
