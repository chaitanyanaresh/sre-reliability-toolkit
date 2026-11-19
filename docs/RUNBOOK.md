# Runbook — High error-budget burn rate

**Alert:** `fast-burn` (page) or `slow-burn` (ticket) from `alerting/`
**Service:** the service named in `slo/config.json`
**Applies when:** burn-rate alert fires, uptime check fails, or users report
widespread errors.

## 1. Triage (first 5 minutes)

1. Acknowledge the page. Start a timer; note the time — the incident record
   needs it.
2. Confirm the alert is real, not a monitoring artifact:
   `python -m slo.report` and
   `python -m alerting.evaluate` — check the per-condition reasons printed
   with the decision.
3. Check service health directly:
   `python -m healthcheck.monitor <service-url>/healthz --rounds 3`
4. Declare severity: **SEV1** if the availability SLO is breached or the
   fast-burn page fired with user-visible impact; **SEV2** for slow-burn /
   partial impact; **SEV3** for ticket-only with no user impact.
5. Open the incident channel and assign roles: incident lead, operator,
   communications. One person leads; everyone else executes.

## 2. Diagnose (next 15 minutes)

1. **What changed?** Recent deploys, config changes, feature flags,
   infrastructure changes. Most incidents correlate with a change.
2. **Where is the error concentrated?** One endpoint, one region, one
   dependency? Compare the burn-rate windows: a 1h burn ≫ 6h burn means the
   problem is *new*; comparable burns mean it has been smoldering.
3. **Dependency check:** database, downstream APIs, cloud provider status.
4. **Capacity check:** `python -m slo.report` capacity outlook — is load
   near the provisioned ceiling? Saturation looks like an outage from the
   user's side.
5. Form a hypothesis and write it in the incident channel *before* acting.

## 3. Mitigate

Prefer the fastest reversible action over the perfect fix:

- Bad deploy → **roll back** to the last known-good revision.
- Bad config/flag → revert the config / disable the flag.
- Single failing dependency → fail over, shed load, or serve degraded
  (cached/static) responses.
- Saturation → scale out within the provisioned limits; shed non-critical
  traffic.
- After each action, re-run `python -m alerting.evaluate` and watch the
  1h burn rate fall. If it does not fall within 10 minutes, escalate.

## 4. Communicate

- Update the incident channel every 15 minutes during SEV1/SEV2, even if
  the update is "still investigating".
- Post a user-facing status update for SEV1: impact, start time, next
  update time. No speculation about root cause externally.
- Record every action and timestamp in the incident channel — this becomes
  the post-incident review timeline.

## 5. Close and review

1. Confirm recovery: 1h burn rate back under 1.0 and health checks green
   for 30 minutes.
2. Generate the review draft:
   `python -m incident.report_generator --alerts-json outputs/alerts.json --out outputs/post_incident_review.md`
3. Complete the post-incident review within 3 business days: root cause,
   timeline, what went well/poorly, and action items with owners and due
   dates. Blameless — the review targets systems, not people.
4. Feed new diagnosis/mitigation steps back into this runbook.
5. Check the remaining error budget (`python -m slo.report`). If the
   incident consumed >50% of the budget, propose a release freeze on
   non-reliability work until the budget recovers — that is what the budget
   is for.

## Post-incident review template

The generator pre-fills impact and detection from monitoring data. The
human sections are: timeline detail, root cause, what went well / poorly,
action items (owner + due date each), and runbook updates. A review with no
action items is not finished.
