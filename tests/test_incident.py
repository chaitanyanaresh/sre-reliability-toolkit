"""Tests for the post-incident review generator."""

from incident.report_generator import build_review

BASE = 1_700_000_000


def test_review_contains_measured_impact():
    # Incident window: 120 minutes x 1000 requests, 60 errors/minute.
    rows = [
        {"ts": BASE + i * 60, "requests": 1000, "errors": 60, "latency_ok": 820}
        for i in range(120)
    ]
    meta = {
        "incident_start": BASE,
        "incident_end": BASE + 120 * 60,
        "description": "Injected incident: elevated 5xx error ratio",
    }
    doc = build_review(meta, rows, decisions=[
        {"rule": "fast-burn", "severity": "page", "fired": True},
        {"rule": "slow-burn", "severity": "ticket", "fired": False},
    ])
    assert "Requests in window: 120,000" in doc
    assert "Errors in window: 7,200" in doc
    assert "fast-burn (page)" in doc
    assert "## Root cause" in doc
    assert "## Action items" in doc
