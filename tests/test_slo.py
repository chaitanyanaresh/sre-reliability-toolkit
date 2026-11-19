"""Tests for the SLO tracker math — all cases are hand-computable."""

from slo import tracker

BASE = 1_700_000_000  # arbitrary fixed epoch anchor


def minute_rows(n, requests, errors, latency_ok=None, start=BASE):
    return [
        {
            "ts": start + i * 60,
            "requests": requests,
            "errors": errors,
            "latency_ok": requests if latency_ok is None else latency_ok,
        }
        for i in range(n)
    ]


def test_window_stats_availability():
    rows = minute_rows(60, requests=100, errors=6)
    stats = tracker.window_stats(rows, BASE + 3600, 1)
    assert stats["requests"] == 6000
    assert stats["errors"] == 360
    assert abs(stats["error_ratio"] - 0.06) < 1e-12
    assert abs(stats["availability"] - 0.94) < 1e-12


def test_window_stats_excludes_outside_window():
    rows = minute_rows(120, requests=100, errors=6)
    stats = tracker.window_stats(rows, BASE + 3600, 1)  # first hour only
    assert stats["requests"] == 6000


def test_burn_rate():
    assert abs(tracker.burn_rate(0.06, 0.999) - 60.0) < 1e-9
    assert abs(tracker.burn_rate(0.001, 0.999) - 1.0) < 1e-9
    assert tracker.burn_rate(0.0, 0.999) == 0.0


def test_error_budget():
    rows = minute_rows(10_000, requests=100, errors=0)
    # add exactly 400 errors spread over the first rows
    for i in range(400):
        rows[i]["errors"] = 1
    budget = tracker.error_budget(rows, 0.999)
    assert budget["requests"] == 1_000_000
    assert abs(budget["budget_events"] - 1000.0) < 1e-6
    assert budget["consumed_events"] == 400
    assert abs(budget["remaining_events"] - 600.0) < 1e-6
    assert abs(budget["remaining_pct"] - 60.0) < 1e-9


def test_budget_exhaustion_days():
    # 48 hourly rows: total requests 960,000 -> budget 960 at 99.9%.
    rows = []
    for h in range(48):
        rows.append({"ts": BASE + h * 3600, "requests": 20_000,
                     "errors": 15, "latency_ok": 19_000})
    # total errors so far: 48*15 = 720 -> remaining 240.
    # Trailing 24h must consume exactly 48/day: set last-24h errors to 2/hour.
    for h in range(24, 48):
        rows[h]["errors"] = 2
    # total errors now: 24*15 + 24*2 = 408 -> remaining 960-408 = 552.
    # exhaustion = 552 / 48 = 11.5 days.
    days = tracker.budget_exhaustion_days(rows, 0.999)
    assert days is not None and abs(days - 11.5) < 1e-9


def test_capacity_projection_linear_growth():
    # Daily totals grow by exactly 10,000/day: 100k, 110k, 120k, 130k.
    rows = []
    for d, total in enumerate([100_000, 110_000, 120_000, 130_000]):
        rows.append({"ts": d * 86400, "requests": total, "errors": 0,
                     "latency_ok": total})
    proj = tracker.capacity_projection(rows, max_rps=200_000 / 86400)
    assert abs(proj["growth_requests_per_day"] - 10_000) < 1e-6
    # intercept 100,000 at day 0; ceiling 200,000/day reached at day 10;
    # last observed day is day 3 -> 7.0 days to ceiling.
    assert proj["days_to_ceiling"] is not None
    assert abs(proj["days_to_ceiling"] - 7.0) < 1e-6


def test_capacity_projection_flat_traffic():
    rows = [{"ts": d * 86400, "requests": 100_000, "errors": 0,
             "latency_ok": 100_000} for d in range(4)]
    proj = tracker.capacity_projection(rows, max_rps=10.0)
    assert proj["days_to_ceiling"] is None
