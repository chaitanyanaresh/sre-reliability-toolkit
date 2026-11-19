"""Build the dashboard's JSON data from the pipeline outputs.

Reads the artifacts the toolkit pipeline already produces —

    outputs/slo_report.json          (SLO attainment, budgets, burn windows)
    outputs/alerts.json              (alert decisions at incident end)
    outputs/post_incident_review.md  (the PIR whose impact figures are
                                      cross-checked by the tests)
    data/request_logs.jsonl          (per-minute request aggregates)
    data/incident_window.json        (incident span metadata)

— and writes two files the dashboard server serves verbatim:

    dashboard/data/summary.json   everything except the time series
    dashboard/data/series.json    trailing-1h burn-rate / error-ratio series

Every number is either copied from the pipeline outputs or recomputed from
the request logs with the *same* definitions the pipeline uses
(``slo.tracker.window_stats`` / ``slo.tracker.burn_rate`` /
``slo.tracker.error_budget`` — the incident impact block replicates the
arithmetic of ``incident.report_generator.build_review`` exactly, and the
test suite asserts it agrees with the generated PIR). Nothing is estimated
or invented.

The summary also carries a health-check snapshot: the health monitor is
polled against a local ``http.server`` fixture (an ``index.html`` in a
temporary directory on 127.0.0.1) — the same fixture style as the
healthcheck demo and tests, never the public internet.

Usage:
    python -m dashboard.build_data [--out-dir dashboard/data]
"""

from __future__ import annotations

import argparse
import functools
import json
import tempfile
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from healthcheck import monitor as health_monitor
from slo import tracker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "dashboard" / "data"

PAGE_THRESHOLD = 14.4   # fast-burn 1h page threshold (alerting/rules.json)
FAST_BURN_6H_THRESHOLD = 6.0  # fast-burn 6h threshold, drawn as reference


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def load_pipeline_outputs(root: Path) -> dict:
    """Load the pipeline artifacts from `root` (project layout)."""
    return {
        "slo_report": json.loads((root / "outputs" / "slo_report.json").read_text()),
        "alerts": json.loads((root / "outputs" / "alerts.json").read_text()),
        "incident_meta": json.loads((root / "data" / "incident_window.json").read_text()),
        "rows": tracker.load_rows(root / "data" / "request_logs.jsonl"),
    }


def compute_incident_impact(rows: list[dict], meta: dict, target: float,
                            decisions: list[dict]) -> dict:
    """Incident impact, computed exactly as incident.report_generator does.

    Requests/errors are summed over [incident_start, incident_end); the
    error ratio comes from tracker.window_stats over the same span; the
    budget share is errors / total error-budget events.
    """
    start, end = int(meta["incident_start"]), int(meta["incident_end"])
    sel = [r for r in rows if start <= r["ts"] < end]
    requests = sum(r["requests"] for r in sel)
    errors = sum(r["errors"] for r in sel)
    stats = tracker.window_stats(rows, end, (end - start) / 3600.0)
    budget = tracker.error_budget(rows, target)
    budget_share = (errors / budget["budget_events"] * 100.0) if budget["budget_events"] else 0.0
    fired = [d for d in decisions if d.get("fired")]
    return {
        "description": meta.get("description", "service incident"),
        "start": _iso(start),
        "end": _iso(end),
        "requests": requests,
        "errors": errors,
        "error_ratio": stats["error_ratio"],
        "budget_share_pct": budget_share,
        "budget_remaining_pct": budget["remaining_pct"],
        "detected_by": [f"{d['rule']} ({d['severity']})" for d in fired],
    }


def compute_series(rows: list[dict], target: float, step_seconds: int = 1800) -> dict:
    """Trailing-1h burn rate and error ratio, sampled every `step_seconds`.

    Uses tracker.window_stats + tracker.burn_rate — the identical code path
    alerting.evaluate uses — so the sample at the incident end reproduces
    the fast-burn 1h figure in outputs/alerts.json.
    """
    if not rows:
        return {"window_hours": 1, "step_seconds": step_seconds, "points": []}
    first_end = rows[0]["ts"] + 3600
    last_end = rows[-1]["ts"] + 60
    points = []
    end_ts = first_end
    while end_ts <= last_end:
        stats = tracker.window_stats(rows, end_ts, 1)
        points.append({
            "ts": end_ts,
            "iso": _iso(end_ts),
            "burn_rate": tracker.burn_rate(stats["error_ratio"], target),
            "error_ratio": stats["error_ratio"],
        })
        end_ts += step_seconds
    return {
        "window_hours": 1,
        "step_seconds": step_seconds,
        "thresholds": [
            {"value": PAGE_THRESHOLD, "label": "fast-burn page threshold (1h)"},
            {"value": FAST_BURN_6H_THRESHOLD, "label": "fast-burn threshold (6h, reference)"},
        ],
        "points": points,
    }


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep build output clean
        pass


def health_snapshot(rounds: int = 3) -> dict:
    """Poll the health monitor against a local http.server fixture.

    Serves a temporary directory containing one index.html on 127.0.0.1
    (ephemeral port): `/` answers 200, `/nonexistent` answers 404 — the
    same fixture behaviour as the toolkit's healthcheck demo. Local only;
    nothing here touches the public internet.
    """
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "index.html").write_text("<!doctype html><title>fixture</title>ok\n")
        handler = functools.partial(_QuietHandler, directory=tmp)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            urls = [base + "/", base + "/nonexistent"]
            summaries = health_monitor.poll(urls, rounds=rounds)
        finally:
            server.shutdown()
    endpoints = {}
    for url, entry in health_monitor.summaries_to_json(summaries).items():
        endpoints[url] = {**entry, "path": urlparse(url).path}
    return {
        "fixture": ("local http.server fixture (temporary directory on "
                    "127.0.0.1, ephemeral port) — not the public internet"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "rounds": rounds,
        "endpoints": endpoints,
    }


def build_summary(root: Path, *, with_health: bool = True) -> dict:
    """Assemble the dashboard summary dict from the pipeline outputs."""
    data = load_pipeline_outputs(root)
    report = data["slo_report"]
    availability = report["slos"]["availability"]
    target = float(availability["target"])

    if any(not slo["met"] for slo in report["slos"].values()):
        status = {"level": "critical", "label": "SLO BREACHED"}
    elif any(d.get("fired") for d in data["alerts"]):
        status = {"level": "warning", "label": "ALERT FIRING"}
    else:
        status = {"level": "ok", "label": "ALL SLOs MET"}

    summary = {
        "service": report["service"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_start": report["data_start"],
        "data_end": report["data_end"],
        "window_days": report["window_days"],
        "status": status,
        "slos": report["slos"],
        "burn_windows": report["burn_windows"],
        "capacity": report["capacity"],
        "alerts": data["alerts"],
        "incident": compute_incident_impact(data["rows"], data["incident_meta"],
                                            target, data["alerts"]),
        "sources": [
            "outputs/slo_report.json",
            "outputs/alerts.json",
            "outputs/post_incident_review.md",
            "data/request_logs.jsonl",
            "data/incident_window.json",
        ],
    }
    if with_health:
        summary["health"] = health_snapshot()
    return summary


def build_all(root: Path = PROJECT_ROOT, out_dir: Path = DEFAULT_OUT_DIR) -> dict:
    """Write summary.json + series.json under `out_dir`; return the summary."""
    root = Path(root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(root)
    target = float(summary["slos"]["availability"]["target"])
    rows = tracker.load_rows(root / "data" / "request_logs.jsonl")
    series = compute_series(rows, target)
    series["incident"] = {"start": summary["incident"]["start"],
                          "end": summary["incident"]["end"]}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "series.json").write_text(json.dumps(series, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT),
                        help="project root (default: this repo)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help="where to write summary.json / series.json")
    args = parser.parse_args()
    summary = build_all(Path(args.root), Path(args.out_dir))
    status = summary["status"]["label"]
    avail = summary["slos"]["availability"]
    print(f"dashboard data written to {args.out_dir}")
    print(f"  service {summary['service']}  status {status}  "
          f"availability {avail['attainment']:.4%} (target {avail['target']:.1%})")


if __name__ == "__main__":
    main()
