# Terraform — Google Cloud deployment & monitoring scaffold

Provisions the cloud footprint for a containerized service and its
observability, in the pattern used when migrating and maintaining
applications on **Google Cloud**:

| File | What it creates |
|---|---|
| `main.tf` | Enables the Run / Monitoring / Logging APIs; deploys the service to **Cloud Run** (min 1 / max 10 instances, 1 CPU / 512 MiB) |
| `monitoring.tf` | A **Cloud Monitoring uptime check** (5-minute period, `/healthz`) and two **alert policies**: uptime failure, and p95 request latency above the SLO threshold (mirrors `../slo/config.json`) |
| `variables.tf` | `project_id` (required), `region`, `service_name`, `container_image`, `latency_threshold_ms`, `notification_channels` (wire the on-call rotation here) |
| `outputs.tf` | Service URL, uptime check ID, alert policy IDs |

## Usage

```bash
cd terraform
terraform init
terraform plan -var project_id=YOUR_PROJECT_ID
terraform apply -var project_id=YOUR_PROJECT_ID
```

## Honest status

**This module was NOT executed or validated in the environment where this
project was authored** — no Terraform binary and no Google Cloud account
were available there. It is provided as reviewed infrastructure-as-code:
read it, run `terraform init` / `terraform validate` / `terraform plan`
against your own project before applying. The default container image is
Google's public sample; point `container_image` at your own Artifact
Registry image for real use, and replace the public invoker binding in
`main.tf` with least-privilege bindings for real callers.
