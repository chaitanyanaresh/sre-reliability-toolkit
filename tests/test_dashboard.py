"""Tests for the dashboard: data build correctness + HTTP smoke test.

Data expectations are cross-checked against the pipeline outputs
themselves (outputs/slo_report.json, outputs/alerts.json and the
generated PIR), never against numbers copied into this file by hand —
except the PIR figures, which are parsed out of the PIR markdown so the
dashboard is verified against the review document it claims to mirror.
"""

import json
import re
import threading
import urllib.request
from pathlib import Path

import pytest

from dashboard import build_data, server as dashboard_server

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def pipeline():
    return {
        "report": json.loads((ROOT / "outputs" / "slo_report.json").read_text()),
        "alerts": json.loads((ROOT / "outputs" / "alerts.json").read_text()),
        "pir": (ROOT / "outputs" / "post_incident_review.md").read_text(),
        "rows": build_data.tracker.load_rows(ROOT / "data" / "request_logs.jsonl"),
        "meta": json.loads((ROOT / "data" / "incident_window.json").read_text()),
    }


@pytest.fixture(scope="module")
def summary(pipeline):
    return build_data.build_summary(ROOT, with_health=False)


def test_summary_matches_slo_report(summary, pipeline):
    report_av = pipeline["report"]["slos"]["availability"]
    av = summary["slos"]["availability"]
    assert av["attainment"] == report_av["attainment"]
    assert av["target"] == report_av["target"]
    assert av["met"] is False
    assert av["error_budget"]["remaining_pct"] == report_av["error_budget"]["remaining_pct"]
    assert av["error_budget"]["consumed_events"] == report_av["error_budget"]["consumed_events"]
    la = summary["slos"]["latency"]
    assert la["attainment"] == pipeline["report"]["slos"]["latency"]["attainment"]
    assert la["met"] is True
    assert summary["status"] == {"level": "critical", "label": "SLO BREACHED"}


def test_summary_alerts_copied_verbatim(summary, pipeline):
    assert summary["alerts"] == pipeline["alerts"]
    fired = {a["rule"] for a in summary["alerts"] if a["fired"]}
    assert fired == {"fast-burn", "slow-burn"}


def test_incident_impact_matches_pir(summary, pipeline):
    inc = summary["incident"]
    pir = pipeline["pir"]
    pir_requests = int(re.search(r"Requests in window: ([\d,]+)", pir).group(1).replace(",", ""))
    pir_errors = int(re.search(r"Errors in window: ([\d,]+)", pir).group(1).replace(",", ""))
    pir_share = float(re.search(r"consumed by this incident: ([\d.]+)%", pir).group(1))
    assert inc["requests"] == pir_requests
    assert inc["errors"] == pir_errors
    assert inc["budget_share_pct"] == pytest.approx(pir_share, abs=0.05)
    assert inc["detected_by"] == ["fast-burn (page)", "slow-burn (ticket)"]


def test_series_reproduces_alert_burn_rate(pipeline):
    target = pipeline["report"]["slos"]["availability"]["target"]
    series = build_data.compute_series(pipeline["rows"], target)
    points = {p["iso"]: p for p in series["points"]}
    # The fast-burn rule's 1h condition in alerts.json, evaluated at the
    # incident end, must be reproduced by the series point at that instant.
    at_end = points["2026-11-17T16:00:00+00:00"]
    alert_1h = next(c for a in pipeline["alerts"] if a["rule"] == "fast-burn"
                    for c in a["conditions"] if c["window_hours"] == 1.0)
    assert at_end["burn_rate"] == pytest.approx(alert_1h["burn_rate"], rel=1e-9)
    assert at_end["burn_rate"] >= 14.4  # page threshold, also drawn on the chart
    assert {t["value"] for t in series["thresholds"]} == {14.4, 6.0}
    # The series peak is the incident-end sample, not some other hour.
    peak = max(series["points"], key=lambda p: p["burn_rate"])
    assert peak["iso"] == "2026-11-17T16:00:00+00:00"


def test_health_snapshot_against_local_fixture():
    health = build_data.health_snapshot(rounds=3)
    by_path = {e["path"]: e for e in health["endpoints"].values()}
    assert by_path["/"]["up"] is True
    assert by_path["/"]["success_rate"] == 1.0
    assert by_path["/nonexistent"]["up"] is False
    assert by_path["/nonexistent"]["success_rate"] == 0.0
    assert "127.0.0.1" in health["fixture"]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("dashboard-data")
    build_data.build_all(ROOT, data_dir)
    srv = dashboard_server.make_server("127.0.0.1", 0, data_dir=data_dir)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_http_index_and_api(live_server, pipeline):
    with urllib.request.urlopen(live_server + "/", timeout=5) as resp:
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        body = resp.read().decode()
    assert "SRE Reliability Dashboard" in body
    assert "/api/summary" in body  # the page is a client of the API

    with urllib.request.urlopen(live_server + "/api/summary", timeout=5) as resp:
        assert resp.status == 200
        assert "application/json" in resp.headers["Content-Type"]
        payload = json.loads(resp.read())
    expected = pipeline["report"]["slos"]["availability"]["attainment"]
    assert payload["slos"]["availability"]["attainment"] == expected
    assert payload["health"]["endpoints"]  # health snapshot was built

    with urllib.request.urlopen(live_server + "/api/series", timeout=5) as resp:
        assert resp.status == 200
        series = json.loads(resp.read())
    assert series["points"], "series must not be empty"
    assert series["incident"]["start"] == "2026-11-17T14:00:00+00:00"
