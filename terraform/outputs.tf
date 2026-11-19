output "service_url" {
  description = "URL of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "uptime_check_id" {
  description = "ID of the Cloud Monitoring uptime check."
  value       = google_monitoring_uptime_check_config.app.id
}

output "alert_policy_ids" {
  description = "IDs of the alert policies created for this service."
  value = [
    google_monitoring_alert_policy.uptime.id,
    google_monitoring_alert_policy.latency.id,
  ]
}
