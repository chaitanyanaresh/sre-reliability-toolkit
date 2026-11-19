# SRE Reliability Toolkit

An **independent skills-demonstration project built by Chaitanya Naresh
Arroju**, aligned to the **CME Group Site Reliability Engineer III** job
description (req 34720). It is my own project, built to demonstrate the
skills that role calls for — site reliability engineering for production
services on Google Cloud: observability, SLOs and error budgets, burn-rate
alerting, incident management and post-incident reviews, capacity planning,
automation that reduces toil, and infrastructure as code. It does not claim
employment at CME Group or anywhere else; every capability below is
demonstrated by code in this repository and by the verified run outputs in
[PROJECT_FACTS.md](PROJECT_FACTS.md).

## What's inside

| Component | What it does | JD duty it demonstrates |
|---|---|---|
| `slo/` | SLO tracker: SLI attainment, error budgets, multi-window burn rates, budget-exhaustion and capacity projections from request data, with a seeded synthetic log generator (including an injected incident) | Observability; monitoring metrics & system health; availability/performance NFRs; capacity planning |
| `alerting/` | Multi-window burn-rate alert rules (fast-burn page, slow-burn ticket, Google SRE workbook style) with per-condition reasons for every decision | Incident detection; on-call paging discipline |
| `healthcheck/` | HTTP endpoint health monitor (status, success rate, mean/p95 latency) | System-health monitoring |
| `incident/` | Post-incident review generator: turns alert + SLO data into a PIR draft pre-filled with measured impact | Post-incident reviews; toil reduction |
| `dashboard/` | Web dashboard over the pipeline outputs: SLO status, error-budget panel, burn-rate chart, alert decisions, incident impact, health checks — stdlib HTTP server + JSON API, zero dependencies | Observability; monitoring metrics & system health (visual) |
| `terraform/` | Google Cloud scaffold: Cloud Run service + Cloud Monitoring uptime check and alert policies (code only — see its README for status) | Migrating/maintaining applications in Google Cloud; IaC |
| `docs/RUNBOOK.md` | Incident runbook: triage → diagnose → mitigate → communicate → review, with the PIR template | Incident management |
| `docs/CAPACITY.md` | Capacity-planning method and how the projection feeds decisions | Capacity planning; resiliency design |
| `scripts/run_all.sh` | One-command end-to-end run of the whole pipeline | Automation |
| `.github/workflows/ci.yml` | CI: pytest + pipeline smoke run on every push | CI/CD hygiene |

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m slo.generate_logs        # synthetic 7-day dataset + injected incident
.venv/bin/python -m slo.report               # SLO / error-budget / burn-rate / capacity report
.venv/bin/python -m alerting.evaluate --at 2026-11-17T16:00:00+00:00   # alerts at incident end
.venv/bin/python -m alerting.evaluate        # alerts at end of data
.venv/bin/python -m incident.report_generator --alerts-json outputs/alerts.json
.venv/bin/python -m healthcheck.monitor http://127.0.0.1:8000/ --rounds 3
.venv/bin/python -m dashboard.server         # web dashboard on http://127.0.0.1:8080/
.venv/bin/python -m pytest tests/ -q         # 20 tests
# or everything at once:
bash scripts/run_all.sh
```

Runtime code uses only the Python 3.12 standard library; pytest is the only
(test-only) dependency.

## Sample output (real, from the seeded dataset)

```
SLO report — checkout-api
Data window: 2026-11-12T00:00:00+00:00 .. 2026-11-19T00:00:00+00:00

[BREACHED] availability SLO target 99.900%, attainment 99.8644%
        error budget: 18,146 events allowed, 24,612 consumed, -35.6% remaining
[MET] latency SLO: 95.0% of requests within 300 ms; attainment 96.78%

Burn rate by window (1.0 = sustainable):
    1h: burn   0.29x  ...   72h: burn   2.52x
```

```
[FIRING] fast-burn (page) @ 2026-11-17T16:00:00+00:00
         ✓ 1h burn rate 60.45x >= threshold 14.4x (7,856 errors / 129,950 requests)
         ✓ 6h burn rate 19.43x >= threshold 6x (16,244 errors / 836,122 requests)
```

The story the data tells: a single 2-hour incident at a ~6% error ratio
consumed 88% of the week's error budget and breached the 99.9% availability
SLO — the fast-burn rule pages while it happens, the slow-burn ticket is
still firing 32 hours later on the 72h window, and the generated
post-incident review quantifies the impact. That is the error-budget
feedback loop working as intended.

## Dashboard

A zero-dependency web front end over the pipeline outputs — the page is a
real client of a real JSON API served by the same process (Python standard
library `http.server` only; charts are inline SVG drawn in vanilla JS; no
CDN, works fully offline).

```bash
bash scripts/run_all.sh                 # pipeline -> outputs/ (+ dashboard data)
.venv/bin/python -m dashboard.server    # http://127.0.0.1:8080/  (--port N to change)
# or explicitly: .venv/bin/python -m dashboard.build_data   # outputs/ -> dashboard/data/*.json
```

Routes: `/` the page · `/api/summary` everything except the time series ·
`/api/series` the burn-rate series · `/healthz` server liveness. If the
data files have not been built yet, the server builds them on startup.

What the page shows (all figures are the pipeline's own outputs, served
verbatim — nothing is recomputed in the browser except chart geometry):

- **Header** — service name, data window, and an overall status pill
  (here: red **SLO BREACHED**, because availability missed its target).
- **SLO cards** — availability attainment vs the 99.9% target with a
  BREACHED badge; latency attainment vs the 95%-within-300 ms target with
  a MET badge; a capacity card (average rps vs the 250 rps ceiling).
- **Error-budget panel** — a bar of budget consumed (135.6% of the
  18,146-event budget) with allowed / consumed / remaining figures.
- **Burn-rate chart** — trailing-1h burn rate over the 7 days on a log
  scale, the 2-hour incident window shaded, dashed threshold lines at
  14.4x (page) and 6x, peaking at 60.45x at the incident end.
- **Alerts panel** — the fast-burn PAGE and slow-burn ticket with the
  per-condition reasons from `outputs/alerts.json`.
- **Incident impact** — the post-incident review's measured impact
  (266,395 requests, 16,004 errors, 88.2% of the budget).
- **Health checks** — a snapshot of the health monitor polled against a
  local `http.server` fixture at data-build time (`/` UP, `/nonexistent`
  DOWN).

## Architecture

```
request aggregates ──► slo.tracker ──► slo.report (CLI + JSON)
                          │                    │
                          ├────► alerting.evaluate (rules.json → decisions + reasons)
                          │                    │
                          └────► incident.report_generator (PIR draft, markdown)
outputs/ + request logs ──► dashboard.build_data ──► dashboard/data/*.json
dashboard.server ──► / (page) + /api/summary + /api/series (stdlib http.server)
healthcheck.monitor ──► independent live-probe path (any HTTP endpoint)
terraform/ ──► the same service + monitoring, as Google Cloud IaC
```

## Extension points

The toolkit is structured to grow component by component:

- **New log sources:** `slo.tracker` consumes per-minute aggregate dicts;
  add an adapter (Cloud Monitoring export, Prometheus, log-file parser)
  that emits the same shape and every downstream tool works unchanged.
- **New SLO types:** add an entry to `slo/config.json` and a branch in
  `slo/report.py::build_report` (availability and latency are the two
  patterns to copy).
- **New alert rules:** append to `alerting/rules.json` — no code change;
  rules are data, evaluated generically with `all`/`any` matching.
- **Notification channels:** alert decisions are plain dicts/JSON, ready
  to be wired to PagerDuty, Slack, or email by a thin sender module; the
  Terraform scaffold takes Cloud Monitoring notification channel IDs.
- **Health checks:** `healthcheck.monitor.poll()` accepts any URL list;
  TCP and gRPC checkers slot in beside `check_once`.
- **Terraform:** the module is parameterized by service name, image, and
  thresholds; additional resources (log-based metrics, dashboards,
  additional services) extend `monitoring.tf` / `main.tf` in the same
  pattern.
- **Incident workflow:** the PIR generator's template sections are plain
  markdown assembly in `incident/report_generator.py::build_review`.
- **Dashboard panels:** the page renders whatever `dashboard.build_data`
  emits; add a field to the summary builder and a block to
  `dashboard/static/index.html` — the API and page stay in lockstep, and
  new series (e.g. latency) follow the `series.json` pattern.

## Honest status

- All Python components were executed end-to-end and are covered by 20
  passing pytest tests — see [PROJECT_FACTS.md](PROJECT_FACTS.md) for the
  exact commands and outputs.
- The Terraform module was **not** executed or validated in the authoring
  environment (no Terraform binary, no Google Cloud account there); it is
  reviewed code, with the caveat stated again in `terraform/README.md`.
- The GitHub Actions workflow is defined in-repo; it runs on GitHub on
  push, and its result was not verified from the authoring environment.
- The dataset is synthetic by design (seeded, deterministic) — the tooling
  is the demonstration, not the data.
