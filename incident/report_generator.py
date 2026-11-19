"""Post-incident review (PIR) generator.

Turns the alerting output and SLO snapshot for a detected incident window
into a structured post-incident review document, pre-filled with everything
the tooling already knows (detection rule, window, error-budget impact) so
the on-call engineer only has to add the human parts: root cause, timeline
detail, and action items. This automates the mechanical half of the
post-incident review — the toil half.

Usage:
    python -m incident.report_generator \
        --meta data/incident_window.json \
        [--slo-json outputs/slo_report.json] [--alerts-json outputs/alerts.json] \
        [--out outputs/post_incident_review.md]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from slo import tracker


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def build_review(meta: dict, rows: list[dict], target: float = 0.999,
                 decisions: list[dict] | None = None) -> str:
    start, end = meta["incident_start"], meta["incident_end"]
    stats = tracker.window_stats(rows, end, (end - start) / 3600.0)
    # window_stats uses [end-hours, end); align exactly to the incident span
    sel = [r for r in rows if start <= r["ts"] < end]
    requests = sum(r["requests"] for r in sel)
    errors = sum(r["errors"] for r in sel)
    budget = tracker.error_budget(rows, target)
    budget_share = (errors / budget["budget_events"] * 100.0) if budget["budget_events"] else 0.0
    fired = [d for d in (decisions or []) if d["fired"]]
    fired_txt = ", ".join(f"{d['rule']} ({d['severity']})" for d in fired) or "see alert evaluation output"

    lines = [
        f"# Post-Incident Review — {meta.get('description', 'service incident')}",
        "",
        f"- **Incident window:** {_iso(start)} .. {_iso(end)}",
        f"- **Detected by:** {fired_txt}",
        f"- **Status:** draft generated from monitoring data — complete the "
        "human sections below",
        "",
        "## Impact (measured from request data)",
        "",
        f"- Requests in window: {requests:,}",
        f"- Errors in window: {errors:,} "
        f"(error ratio {stats['error_ratio']:.2%})",
        f"- Share of the {budget['requests']:,}-request error budget consumed "
        f"by this incident: {budget_share:.1f}%",
        f"- Error budget remaining after the window: {budget['remaining_pct']:.1f}%",
        "",
        "## Timeline",
        "",
        f"- {_iso(start)} — error ratio leaves the baseline band (monitoring data)",
        f"- {_iso(end)} — error ratio returns to baseline (monitoring data)",
        "- _add: page acknowledged, mitigation started, mitigation verified_",
        "",
        "## Root cause",
        "",
        "_To be completed by the incident owner._",
        "",
        "## What went well / what went poorly",
        "",
        "_To be completed in the review meeting._",
        "",
        "## Action items",
        "",
        "| # | Action | Owner | Due |",
        "|---|---|---|---|",
        "| 1 | _e.g. add dashboard panel for the failing SLI_ |  |  |",
        "| 2 | _e.g. tune alert threshold / add runbook step_ |  |  |",
        "",
        "## Lessons for the runbook",
        "",
        "_Feed any new diagnosis or mitigation steps back into docs/RUNBOOK.md._",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", default="data/incident_window.json")
    parser.add_argument("--data", default="data/request_logs.jsonl")
    parser.add_argument("--alerts-json", default=None)
    parser.add_argument("--out", default="outputs/post_incident_review.md")
    args = parser.parse_args()

    meta = json.loads(Path(args.meta).read_text())
    rows = tracker.load_rows(args.data)
    decisions = (json.loads(Path(args.alerts_json).read_text())
                 if args.alerts_json else None)
    doc = build_review(meta, rows, decisions=decisions)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"wrote post-incident review draft to {out}")


if __name__ == "__main__":
    main()
