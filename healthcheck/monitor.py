"""Service health monitor.

Polls a list of HTTP endpoints, records status and latency for every check,
and prints a summary (up/down, success rate, mean and p95 latency). Uses
only the standard library (urllib). A check counts as healthy when the
endpoint answers with a 2xx/3xx status inside the timeout.

Usage:
    python -m healthcheck.monitor URL [URL ...] [--rounds 5] [--timeout 2]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    url: str
    ok: bool
    status: int | None
    latency_ms: float
    error: str | None = None


@dataclass
class EndpointSummary:
    url: str
    checks: int = 0
    successes: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successes / self.checks if self.checks else 0.0

    @property
    def up(self) -> bool:
        return self.checks > 0 and self.success_rate == 1.0

    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        idx = min(len(ordered) - 1, int(0.95 * len(ordered)))
        return ordered[idx]

    def mean_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0


def check_once(url: str, timeout: float = 2.0) -> CheckResult:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sre-healthcheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
        latency = (time.perf_counter() - start) * 1000.0
        return CheckResult(url, 200 <= status < 400, status, latency)
    except urllib.error.HTTPError as exc:  # server answered with an error status
        latency = (time.perf_counter() - start) * 1000.0
        return CheckResult(url, False, exc.code, latency, f"HTTP {exc.code}")
    except Exception as exc:  # connection error, timeout, DNS, ...
        latency = (time.perf_counter() - start) * 1000.0
        return CheckResult(url, False, None, latency, type(exc).__name__)


def poll(urls: list[str], rounds: int = 3, timeout: float = 2.0,
         interval: float = 0.0) -> dict[str, EndpointSummary]:
    summaries = {u: EndpointSummary(url=u) for u in urls}
    for rnd in range(rounds):
        for url in urls:
            result = check_once(url, timeout)
            s = summaries[url]
            s.checks += 1
            s.successes += 1 if result.ok else 0
            s.latencies_ms.append(result.latency_ms)
        if interval and rnd < rounds - 1:
            time.sleep(interval)
    return summaries


def format_summaries(summaries: dict[str, EndpointSummary]) -> str:
    lines = []
    for url, s in summaries.items():
        state = "UP  " if s.up else "DOWN"
        lines.append(
            f"[{state}] {url}  success {s.success_rate:.0%} "
            f"({s.successes}/{s.checks})  mean {s.mean_latency_ms():.1f} ms  "
            f"p95 {s.p95_latency_ms():.1f} ms"
        )
    return "\n".join(lines)


def summaries_to_json(summaries: dict[str, EndpointSummary]) -> dict:
    return {
        url: {
            "up": s.up,
            "checks": s.checks,
            "successes": s.successes,
            "success_rate": s.success_rate,
            "mean_latency_ms": s.mean_latency_ms(),
            "p95_latency_ms": s.p95_latency_ms(),
        }
        for url, s in summaries.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    summaries = poll(args.urls, rounds=args.rounds, timeout=args.timeout)
    print(format_summaries(summaries))
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(summaries_to_json(summaries), fh, indent=2)
        print(f"wrote JSON summary to {args.json_out}")


if __name__ == "__main__":
    main()
