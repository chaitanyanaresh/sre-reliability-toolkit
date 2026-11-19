"""SLO report CLI.

Reads an SLO config and per-minute request aggregates, then prints a
readable reliability report: SLI attainment vs target, error-budget
remaining, multi-window burn rates, a budget-exhaustion projection, and a
capacity outlook. Optionally writes the same numbers as JSON for the
alerting and incident tooling.

Usage:
    python -m slo.report [--config slo/config.json] [--data data/request_logs.jsonl]
                         [--json-out outputs/slo_report.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import tracker


def build_report(config: dict, rows: list[dict]) -> dict:
    end_ts = rows[-1]["ts"] + 60 if rows else 0
    report: dict = {
        "service": config["service"],
        "window_days": config.get("window_days"),
        "data_start": datetime.fromtimestamp(rows[0]["ts"], timezone.utc).isoformat() if rows else None,
        "data_end": datetime.fromtimestamp(end_ts, timezone.utc).isoformat() if rows else None,
        "slos": {},
        "burn_windows": {},
    }
    for slo in config["slos"]:
        target = slo["target"]
        if slo["type"] == "availability":
            budget = tracker.error_budget(rows, target)
            windows = {}
            for hours in tracker.WINDOWS_HOURS:
                stats = tracker.window_stats(rows, end_ts, hours)
                windows[f"{hours}h"] = {
                    **stats,
                    "burn_rate": tracker.burn_rate(stats["error_ratio"], target),
                }
            report["slos"][slo["name"]] = {
                "type": "availability",
                "target": target,
                "attainment": budget["availability"],
                "met": budget["availability"] >= target,
                "error_budget": budget,
                "exhaustion_days_at_24h_burn": tracker.budget_exhaustion_days(rows, target),
            }
            report["burn_windows"] = windows
        elif slo["type"] == "latency":
            total = sum(r["requests"] for r in rows)
            ok = sum(r["latency_ok"] for r in rows)
            attainment = (ok / total) if total else 1.0
            report["slos"][slo["name"]] = {
                "type": "latency",
                "threshold_ms": slo["threshold_ms"],
                "target": target,
                "attainment": attainment,
                "met": attainment >= target,
            }
    cap = config.get("capacity")
    if cap:
        report["capacity"] = tracker.capacity_projection(rows, cap["max_rps"])
    return report


def format_report(report: dict) -> str:
    lines = []
    lines.append(f"SLO report — {report['service']}")
    lines.append(f"Data window: {report['data_start']} .. {report['data_end']}")
    lines.append("")
    for name, s in report["slos"].items():
        status = "MET" if s["met"] else "BREACHED"
        if s["type"] == "availability":
            lines.append(
                f"[{status}] availability SLO target {s['target']:.3%}, "
                f"attainment {s['attainment']:.4%}"
            )
            b = s["error_budget"]
            lines.append(
                f"        error budget: {b['budget_events']:,.0f} events allowed, "
                f"{b['consumed_events']:,} consumed, {b['remaining_pct']:.1f}% remaining"
            )
            exh = s["exhaustion_days_at_24h_burn"]
            lines.append(
                "        budget exhaustion at trailing-24h burn: "
                + (f"~{exh:.1f} days" if exh is not None else "n/a (budget exhausted or no burn)")
            )
        else:
            lines.append(
                f"[{status}] latency SLO: {s['target']:.1%} of requests within "
                f"{s['threshold_ms']} ms; attainment {s['attainment']:.2%}"
            )
    if report["burn_windows"]:
        lines.append("")
        lines.append("Burn rate by window (1.0 = sustainable):")
        for label, w in report["burn_windows"].items():
            lines.append(
                f"  {label:>4}: burn {w['burn_rate']:6.2f}x  "
                f"(error ratio {w['error_ratio']:.4%}, {w['errors']:,} errors / {w['requests']:,} requests)"
            )
    cap = report.get("capacity")
    if cap:
        lines.append("")
        lines.append("Capacity outlook:")
        lines.append(f"  average load {cap['avg_rps']:.1f} rps vs ceiling {cap['ceiling_rps']:.0f} rps")
        lines.append(
            f"  fitted growth {cap['growth_requests_per_day']:+,.0f} requests/day "
            f"({cap['growth_pct_per_day']:+.2f}%/day)"
        )
        dtc = cap["days_to_ceiling"]
        lines.append(
            "  days until average load reaches ceiling: "
            + (f"~{dtc:.0f}" if dtc is not None else "n/a (flat or shrinking traffic)")
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="slo/config.json")
    parser.add_argument("--data", default="data/request_logs.jsonl")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    rows = tracker.load_rows(args.data)
    report = build_report(config, rows)
    print(format_report(report))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote JSON report to {out}")


if __name__ == "__main__":
    main()
