"""SLO tracker: SLI attainment, error budgets, burn rates, capacity outlook.

Works on per-minute aggregate rows ({"ts", "requests", "errors",
"latency_ok"}) such as those produced by slo.generate_logs — the same shape
an aggregated metrics export provides. All math is plain arithmetic on those
aggregates, so every number in the report can be checked by hand.

Definitions (Google SRE workbook):
  * availability SLI   = 1 - errors / requests
  * latency SLI        = latency_ok / requests   (requests within threshold)
  * error budget       = (1 - target) * requests over the SLO window
  * budget remaining % = (budget - errors) / budget * 100
  * burn rate          = observed error ratio / (1 - target)
                         (1.0 = consuming budget exactly as fast as allowed)
"""

from __future__ import annotations

import json
from pathlib import Path

WINDOWS_HOURS = (1, 6, 24, 72)


def load_rows(path: str | Path) -> list[dict]:
    rows = []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["ts"])
    return rows


def window_stats(rows: list[dict], end_ts: int, hours: float) -> dict:
    """Aggregate stats for the trailing `hours` ending at `end_ts`."""
    start_ts = end_ts - int(hours * 3600)
    sel = [r for r in rows if start_ts <= r["ts"] < end_ts]
    requests = sum(r["requests"] for r in sel)
    errors = sum(r["errors"] for r in sel)
    latency_ok = sum(r["latency_ok"] for r in sel)
    return {
        "hours": hours,
        "requests": requests,
        "errors": errors,
        "error_ratio": (errors / requests) if requests else 0.0,
        "availability": (1.0 - errors / requests) if requests else 1.0,
        "latency_ok_ratio": (latency_ok / requests) if requests else 1.0,
    }


def burn_rate(error_ratio: float, target: float) -> float:
    """Burn rate relative to an availability target (e.g. 0.999)."""
    allowed = 1.0 - target
    if allowed <= 0:
        raise ValueError("target must be < 1.0")
    return error_ratio / allowed


def error_budget(rows: list[dict], target: float) -> dict:
    """Error budget over the full span covered by `rows`."""
    requests = sum(r["requests"] for r in rows)
    errors = sum(r["errors"] for r in rows)
    budget = (1.0 - target) * requests
    consumed = errors
    remaining = budget - consumed
    return {
        "requests": requests,
        "errors": errors,
        "budget_events": budget,
        "consumed_events": consumed,
        "remaining_events": remaining,
        "remaining_pct": (remaining / budget * 100.0) if budget else 100.0,
        "availability": (1.0 - errors / requests) if requests else 1.0,
    }


def budget_exhaustion_days(rows: list[dict], target: float) -> float | None:
    """Days until the error budget is exhausted at the trailing-24h burn.

    Returns None when the budget is already exhausted or the 24h burn is 0.
    """
    if not rows:
        return None
    end_ts = rows[-1]["ts"] + 60
    stats24 = window_stats(rows, end_ts, 24)
    budget = error_budget(rows, target)
    if budget["remaining_events"] <= 0:
        return None
    daily_consumption = stats24["errors"]  # errors in the trailing 24h
    if daily_consumption <= 0:
        return None
    return budget["remaining_events"] / daily_consumption


def capacity_projection(rows: list[dict], max_rps: float) -> dict:
    """Project traffic growth from daily totals (least-squares fit).

    Returns the current average rps, the fitted daily growth rate, and the
    estimated days until average daily traffic reaches the provisioned
    ceiling (None if traffic is flat/shrinking or already above it).
    """
    if not rows:
        return {"avg_rps": 0.0, "growth_per_day": 0.0, "days_to_ceiling": None}
    day_seconds = 86400
    first_day = rows[0]["ts"] // day_seconds
    daily: dict[int, int] = {}
    for r in rows:
        d = r["ts"] // day_seconds - first_day
        daily[d] = daily.get(d, 0) + r["requests"]
    days = sorted(daily)
    xs = [float(d) for d in days]
    ys = [float(daily[d]) for d in days]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = (sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom) if denom else 0.0
    intercept = mean_y - slope * mean_x
    avg_rps = mean_y / day_seconds
    ceiling_per_day = max_rps * day_seconds
    days_to_ceiling: float | None
    if mean_y >= ceiling_per_day:
        days_to_ceiling = 0.0
    elif slope <= 0:
        days_to_ceiling = None
    else:
        days_to_ceiling = (ceiling_per_day - intercept) / slope - xs[-1]
    return {
        "avg_rps": avg_rps,
        "daily_requests_last": ys[-1],
        "growth_requests_per_day": slope,
        "growth_pct_per_day": (slope / mean_y * 100.0) if mean_y else 0.0,
        "ceiling_rps": max_rps,
        "days_to_ceiling": days_to_ceiling,
    }
