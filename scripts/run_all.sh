#!/usr/bin/env bash
# End-to-end demo: generate data, then run every tool in the toolkit.
# Usage: bash scripts/run_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

echo "== 1/6 Generate synthetic request logs (seed 42) =="
$PY -m slo.generate_logs

echo
echo "== 2/6 SLO report =="
$PY -m slo.report --json-out outputs/slo_report.json

echo
echo "== 3/6 Alert evaluation at the end of the incident window =="
$PY -m alerting.evaluate --at 2026-11-17T16:00:00+00:00 --json-out outputs/alerts.json

echo
echo "== 4/6 Alert evaluation at the end of the data window =="
$PY -m alerting.evaluate

echo
echo "== 5/6 Post-incident review draft =="
$PY -m incident.report_generator --alerts-json outputs/alerts.json

echo
echo "== 6/6 Build dashboard data =="
$PY -m dashboard.build_data

echo
echo "Done. Outputs in outputs/ (health monitor demo: start any local HTTP"
echo "server and run: python3 -m healthcheck.monitor <url> --rounds 3;"
echo "dashboard: python3 -m dashboard.server, then open http://127.0.0.1:8080/)"
