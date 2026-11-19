# Observability scaffold for the Cloud Run service: an uptime check plus
# two alert policies (availability and latency), mirroring the burn-rate
# alerting implemented in Python under ../alerting/.

resource "google_monitoring_uptime_check_config" "app" {
  display_name = "${var.service_name}-uptime"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/healthz"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.app.uri, "https://")
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "uptime" {
  display_name = "${var.service_name} uptime check failing"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failure"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  notification_channels = var.notification_channels

  documentation {
    content   = "Uptime check for ${var.service_name} is failing. Start with docs/RUNBOOK.md: confirm scope, check recent changes, then mitigate."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "latency" {
  display_name = "${var.service_name} latency above SLO threshold"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run request latency p95"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_latencies\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.latency_threshold_ms
      duration        = "600s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MEAN"
      }
    }
  }

  notification_channels = var.notification_channels

  documentation {
    content   = "p95 latency for ${var.service_name} exceeded ${var.latency_threshold_ms} ms for 10 minutes. Compare against the latency SLO in slo/config.json and follow docs/RUNBOOK.md."
    mime_type = "text/markdown"
  }
}
