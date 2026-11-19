"""Tests for burn-rate alert evaluation on hand-computed scenarios."""

import json
from pathlib import Path

from alerting.evaluate import evaluate_rules

BASE = 1_700_000_000
RULES = json.loads(
    (Path(__file__).parent.parent / "alerting" / "rules.json").read_text()
)["rules"]


def rows_with_profile(profile):
    """profile: list of (minutes, errors_per_minute) at 1000 requests/min."""
    rows = []
    i = 0
    for minutes, errors in profile:
        for _ in range(minutes):
            rows.append({"ts": BASE + i * 60, "requests": 1000,
                         "errors": errors, "latency_ok": 970})
            i += 1
    return rows


def decisions_by_name(rows, at_ts):
    return {d["rule"]: d for d in evaluate_rules(rows, RULES, at_ts)}


def test_fast_burn_pages():
    # 5h at 0.5% errors (burn 5), then 1h at 2% (burn 20).
    # 1h burn = 20 >= 14.4; 6h burn = (300*5 + 60*20)/360000 / 0.001 = 7.5 >= 6.
    rows = rows_with_profile([(300, 5), (60, 20)])
    at = BASE + 360 * 60
    d = decisions_by_name(rows, at)
    assert d["fast-burn"]["fired"] is True
    assert d["fast-burn"]["severity"] == "page"
    reasons = " ".join(c["reason"] for c in d["fast-burn"]["conditions"])
    assert "20.00x" in reasons and "7.50x" in reasons


def test_sustained_burn_tickets_without_paging():
    # Uniform 0.2% error ratio = burn 2.0: too slow to page, but the 72h
    # condition (>= 1.0x) fires a ticket.
    rows = rows_with_profile([(360, 2)])
    at = BASE + 360 * 60
    d = decisions_by_name(rows, at)
    assert d["fast-burn"]["fired"] is False
    assert d["slow-burn"]["fired"] is True
    assert d["slow-burn"]["severity"] == "ticket"


def test_healthy_service_fires_nothing():
    # Baseline 0.04% error ratio = burn 0.4: no rule fires.
    rows = []
    for i in range(360):
        rows.append({"ts": BASE + i * 60, "requests": 10_000, "errors": 4,
                     "latency_ok": 9700})
    at = BASE + 360 * 60
    d = decisions_by_name(rows, at)
    assert d["fast-burn"]["fired"] is False
    assert d["slow-burn"]["fired"] is False
