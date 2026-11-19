"""Multi-window burn-rate alert evaluation.

Evaluates alert rules (alerting/rules.json) against burn rates computed by
the SLO tracker at a chosen reference time. Each decision carries the
per-condition evidence so an on-call engineer can see *why* an alert did or
did not fire — no black-box paging.

Rule shape:
    {"name": ..., "severity": "page"|"ticket", "match": "all"|"any",
     "conditions": [{"window_hours": 1, "burn_rate_gte": 14.4}, ...]}

Usage:
    python -m alerting.evaluate [--data data/request_logs.jsonl]
                                [--at ISO8601]   # default: end of data
                                [--json-out outputs/alerts.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from slo import tracker

DEFAULT_TARGET = 0.999  # availability target from slo/config.json


def evaluate_rules(rows: list[dict], rules: list[dict], at_ts: int,
                   target: float = DEFAULT_TARGET) -> list[dict]:
    """Return one decision dict per rule, evaluated at `at_ts`."""
    windows: dict[float, dict] = {}
    decisions = []
    for rule in rules:
        condition_results = []
        for cond in rule["conditions"]:
            hours = float(cond["window_hours"])
            if hours not in windows:
                stats = tracker.window_stats(rows, at_ts, hours)
                stats = {**stats, "burn_rate": tracker.burn_rate(stats["error_ratio"], target)}
                windows[hours] = stats
            w = windows[hours]
            fired = w["burn_rate"] >= float(cond["burn_rate_gte"])
            condition_results.append({
                "window_hours": hours,
                "burn_rate": w["burn_rate"],
                "threshold": float(cond["burn_rate_gte"]),
                "fired": fired,
                "reason": (
                    f"{hours:g}h burn rate {w['burn_rate']:.2f}x "
                    f"{'>=' if fired else '<'} threshold {float(cond['burn_rate_gte']):g}x "
                    f"({w['errors']:,} errors / {w['requests']:,} requests)"
                ),
            })
        if rule.get("match", "all") == "all":
            fired = all(c["fired"] for c in condition_results)
        else:
            fired = any(c["fired"] for c in condition_results)
        decisions.append({
            "rule": rule["name"],
            "severity": rule["severity"],
            "fired": fired,
            "evaluated_at": datetime.fromtimestamp(at_ts, timezone.utc).isoformat(),
            "conditions": condition_results,
        })
    return decisions


def format_decisions(decisions: list[dict]) -> str:
    lines = []
    for d in decisions:
        state = "FIRING" if d["fired"] else "ok"
        lines.append(f"[{state:>6}] {d['rule']} ({d['severity']}) @ {d['evaluated_at']}")
        for c in d["conditions"]:
            mark = "✓" if c["fired"] else "·"
            lines.append(f"         {mark} {c['reason']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/request_logs.jsonl")
    parser.add_argument("--rules", default="alerting/rules.json")
    parser.add_argument("--config", default="slo/config.json")
    parser.add_argument("--at", default=None, help="ISO8601 reference time; default = end of data")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    rows = tracker.load_rows(args.data)
    rules = json.loads(Path(args.rules).read_text())["rules"]
    config = json.loads(Path(args.config).read_text())
    target = next(s["target"] for s in config["slos"] if s["type"] == "availability")
    at_ts = (int(datetime.fromisoformat(args.at).timestamp())
             if args.at else rows[-1]["ts"] + 60)

    decisions = evaluate_rules(rows, rules, at_ts, target)
    print(format_decisions(decisions))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(decisions, indent=2) + "\n")
        print(f"\nwrote alert decisions to {out}")


if __name__ == "__main__":
    main()
