# PROJECT_FACTS — SRE Reliability Toolkit

Only facts verified by actually running the code in this repository on
2026-11-19. Nothing here is estimated or aspirational. This project is an
independent skills-demonstration project by Chaitanya Naresh Arroju,
aligned to the CME Group Site Reliability Engineer III job description
(req 34720); it claims no employment at any company.

## Environment

- Python 3.12.3; pytest 9.2.0 (project-local `.venv`); runtime code is
  standard library only.
- Terraform: **not installed** in the authoring environment, and no Google
  Cloud account was available — see the Terraform row in the mapping table.

## Tests

Command: `.venv/bin/python -m pytest tests/ -q`
Result: **20 passed, 0 failed** (3 alerting, 3 healthcheck, 1 incident,
7 SLO — including hand-computed burn-rate, error-budget, exhaustion, and
capacity-projection cases; health checks run against a local fixture HTTP
server, never the public internet — plus 6 dashboard tests added
2026-11-19: summary/series correctness cross-checked against the pipeline
outputs and the generated PIR, a health-snapshot test against a local
fixture, and an HTTP smoke test of the dashboard server).

## Verified run outputs

**Data generation** — `python -m slo.generate_logs`
→ 10,080 minute rows; 18,146,367 requests; 24,612 errors; seed 42;
injected incident 2026-11-17T14:00–16:00 UTC.

**SLO report** — `python -m slo.report`
→ availability attainment **99.8644% vs 99.9% target: BREACHED**; error
budget 18,146 events allowed / 24,612 consumed / **−35.6% remaining**;
latency SLO **MET** (96.78% within 300 ms vs 95% target); burn rates at end
of data: 1h **0.29x**, 6h **0.51x**, 24h **0.48x**, 72h **2.52x**; capacity:
average load **30.0 rps** vs 250 rps ceiling, fitted growth ~0 → days to
ceiling n/a (flat synthetic traffic, as designed).

**Alert evaluation at incident end** — `python -m alerting.evaluate --at 2026-11-17T16:00:00+00:00`
→ **fast-burn PAGE firing** (1h burn 60.45x ≥ 14.4; 6h burn 19.43x ≥ 6);
slow-burn firing.

**Alert evaluation at end of data** — `python -m alerting.evaluate`
→ fast-burn ok; **slow-burn TICKET still firing** (72h burn 2.52x ≥ 1.0).

**Health monitor** — `python -m healthcheck.monitor` against a local
`http.server` fixture, 3 rounds
→ `/` **UP**, success 100% (3/3), mean 12.6 ms, p95 35.0 ms;
`/nonexistent` **DOWN**, success 0% (0/3).

**Post-incident review** — `python -m incident.report_generator --alerts-json outputs/alerts.json`
→ draft written to `outputs/post_incident_review.md`: incident window
266,395 requests / 16,004 errors (6.01%); the incident consumed **88.2%**
of the 7-day error budget; detected-by line names both fired rules.

**End-to-end script** — `bash scripts/run_all.sh` → all six stages exit 0
(sixth stage added 2026-11-19: dashboard data build).

**Web dashboard (strengthening round 1, 2026-11-19)** —
`python -m dashboard.build_data` → wrote `dashboard/data/summary.json` +
`series.json`; `python -m dashboard.server --port 8091` + `curl`:
→ `GET /` **200**, 12,721 bytes of HTML; `GET /api/summary` **200** JSON
with availability attainment **0.9986436954570576 (99.8644%)** — identical
to `outputs/slo_report.json` — status `SLO BREACHED`, error budget
18,146 allowed / 24,612 consumed / −35.6% remaining, latency attainment
96.78% MET; `GET /api/series` **200** with **335 points** (trailing-1h
burn rate every 30 min) whose peak **60.45x at 2026-11-17T16:00:00Z**
reproduces the fast-burn 1h figure in `outputs/alerts.json` exactly (same
`slo.tracker` code path); unknown route → **404**. The data build's
health snapshot polled the monitor against a local `http.server` fixture:
`/` **UP** 100% (3/3), `/nonexistent` **DOWN** 0% (0/3). The dashboard
supports JD rows 2, 3 and 7 (observability, monitoring/reports,
automation) with a visual front end; it introduces no new claims.

## JD mapping — CME Group Site Reliability Engineer III (req 34720)

JD source: the role's published duties and minimum requirements. "Demonstrated"
means the code in this repo does it and the run output above proves it.

| # | JD requirement | Demonstrated? | How |
|---|---|---|---|
| 1 | Migrate and maintain applications in **Google Cloud**, working with development & platform engineering teams | **Partially — as code only** | `terraform/` provisions a Cloud Run service + APIs on GCP. **Not executed or validated**: no Terraform binary or GCP account in the authoring environment. The cross-team collaboration aspect is an employment duty and is not claimed. |
| 2 | Apply **observability** concepts and applications to maintain services | **Demonstrated** | SLO tracker (SLIs, budgets, burn rates), health monitor, the web dashboard (`dashboard/` — SLO status, error-budget panel, burn-rate chart over the pipeline outputs), and the Cloud Monitoring scaffold in `terraform/monitoring.tf` (GCP side is code only). |
| 3 | **Monitor metrics and system health; analyze reports** | **Demonstrated** | `slo.report` CLI report, `healthcheck.monitor` runs, and the dashboard's `/api/summary` + `/api/series` JSON — real outputs above. |
| 4 | Provide **on-call rotation support** for production systems | **Not demonstrated** | An employment duty; cannot be evidenced by a project. The paging-grade alert rules and runbook are the supporting artifacts an on-call rotation uses. |
| 5 | Facilitate **incident management**; conduct **post-incident reviews** | **Demonstrated in part** | `docs/RUNBOOK.md` incident process; burn-rate detection fired on the injected incident; `incident.report_generator` produced a PIR draft pre-filled with measured impact (88.2% of budget). Facilitation itself is a team duty. |
| 6 | Designs for **operational resiliency, fault tolerance, and capacity planning** | **Demonstrated in part** | Capacity projection computed from data (`slo/tracker.py`, method in `docs/CAPACITY.md`, math unit-tested with hand-computed growth data); resiliency/fault-tolerance patterns documented in the runbook (rollback, failover, load shedding) and scaling bounds in the Terraform scaffold. |
| 7 | Continually improve processes; promote and implement **automation**; **manage toil** | **Demonstrated** | The whole pipeline is automated end-to-end (`scripts/run_all.sh`): data → report → alert decisions → PIR draft; CI workflow runs tests + smoke run on push (workflow defined; its GitHub-side result not verified from here). |
| 8 | Ensure solutions meet **non-functional requirements: availability, performance, security, maintainability** | **Partially demonstrated** | Availability and performance are measured SLOs with reports (rows 2–3). Maintainability: modular stdlib code + 20 passing tests. Security: limited to hygiene (no secrets in code, least-privilege guidance in the Terraform README) — no security tooling is claimed. |
| 9 | Minimum requirements: Bachelor's degree + 36 months of experience | **Not demonstrated** | Credential/experience requirement — out of scope for a project by definition; nothing here speaks to it. |

## Not executed / not verified (stated plainly)

- Terraform module: not run (`terraform` unavailable; no GCP account).
- GitHub Actions workflow: defined, not verified from this environment.
- Health monitor demo used a local fixture server, not the public internet.
- All request data is synthetic (seeded, deterministic) by design.
