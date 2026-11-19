"""Synthetic request-log generator for the SLO tracker.

Produces one aggregate record per minute (the shape a real metrics pipeline
exports after aggregation): timestamp, request count, error count, and the
count of requests inside the latency threshold. A fixed seed makes the data
fully deterministic, and a documented incident window is injected so the
alerting pipeline has something real to detect:

  * baseline error ratio  ~0.04%  (inside a 99.9% availability budget)
  * incident, day 6 14:00-16:00 UTC: error ratio ~6%, latency degraded

Usage:
    python -m slo.generate_logs [--out data/request_logs.jsonl]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

SEED = 42
DAYS = 7
START = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)  # fixed anchor
BASE_RPM = 2400.0  # baseline requests per minute (~40 rps average)
BASE_ERROR_RATIO = 0.0004
BASE_LATENCY_OK_RATIO = 0.97
INCIDENT_DAY = 5  # 6th day of the window (0-based)
INCIDENT_START_MIN = 14 * 60
INCIDENT_END_MIN = 16 * 60
INCIDENT_ERROR_RATIO = 0.06
INCIDENT_LATENCY_OK_RATIO = 0.82


def incident_window() -> tuple[int, int]:
    """Epoch-second (start, end) of the injected incident."""
    start = int(START.timestamp()) + (INCIDENT_DAY * 1440 + INCIDENT_START_MIN) * 60
    end = int(START.timestamp()) + (INCIDENT_DAY * 1440 + INCIDENT_END_MIN) * 60
    return start, end


def generate(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    inc_start, inc_end = incident_window()
    rows: list[dict] = []
    start_ts = int(START.timestamp())
    for minute in range(DAYS * 1440):
        ts = start_ts + minute * 60
        minute_of_day = minute % 1440
        diurnal = 0.75 + 0.25 * math.sin((minute_of_day - 360) / 1440.0 * 2 * math.pi)
        rpm = max(200.0, BASE_RPM * diurnal + rng.gauss(0, 90))
        requests = int(round(rpm))
        in_incident = inc_start <= ts < inc_end
        err_ratio = INCIDENT_ERROR_RATIO if in_incident else BASE_ERROR_RATIO
        lat_ok_ratio = INCIDENT_LATENCY_OK_RATIO if in_incident else BASE_LATENCY_OK_RATIO
        errors = int(round(requests * err_ratio * rng.uniform(0.85, 1.15)))
        latency_ok = int(round(requests * lat_ok_ratio * rng.uniform(0.99, 1.01)))
        latency_ok = min(latency_ok, requests)
        rows.append(
            {
                "ts": ts,
                "requests": requests,
                "errors": errors,
                "latency_ok": latency_ok,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/request_logs.jsonl")
    parser.add_argument("--meta-out", default="data/incident_window.json")
    args = parser.parse_args()

    rows = generate()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    inc_start, inc_end = incident_window()
    meta = {
        "incident_start": inc_start,
        "incident_end": inc_end,
        "incident_start_iso": datetime.fromtimestamp(inc_start, timezone.utc).isoformat(),
        "incident_end_iso": datetime.fromtimestamp(inc_end, timezone.utc).isoformat(),
        "description": "Injected incident: elevated 5xx error ratio (~6%) and degraded latency",
        "seed": SEED,
    }
    Path(args.meta_out).write_text(json.dumps(meta, indent=2) + "\n")
    total = sum(r["requests"] for r in rows)
    errors = sum(r["errors"] for r in rows)
    print(f"wrote {len(rows)} minute rows to {out} "
          f"({total:,} requests, {errors:,} errors, seed={SEED})")
    print(f"incident window: {meta['incident_start_iso']} .. {meta['incident_end_iso']}")


if __name__ == "__main__":
    main()
