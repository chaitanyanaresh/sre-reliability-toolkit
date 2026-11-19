"""Dashboard web server — Python standard library only.

Serves the single-page dashboard and its JSON API:

    GET /              dashboard page (dashboard/static/index.html)
    GET /api/summary   dashboard/data/summary.json  (built by build_data)
    GET /api/series    dashboard/data/series.json   (burn-rate time series)
    GET /healthz       {"ok": true} liveness probe for the server itself

If the data files have not been built yet, the server builds them on
startup (same code path as ``python -m dashboard.build_data``), so the
one-command flow after the pipeline is just:

    python -m dashboard.server [--port 8080]

No third-party packages, no build step; the page works fully offline.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dashboard import build_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"


def _make_handler(data_dir: Path, static_dir: Path):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "sre-dashboard/1.0"

        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, code: int, obj) -> None:
            self._send(code, (json.dumps(obj, indent=2) + "\n").encode(),
                       "application/json")

        def _send_file(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self._send_json(404, {"error": f"not built: {path.name} — "
                                      "run python -m dashboard.build_data"})
                return
            self._send(200, path.read_bytes(), content_type)

        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]
            if route == "/":
                self._send_file(static_dir / "index.html",
                                "text/html; charset=utf-8")
            elif route == "/api/summary":
                self._send_file(data_dir / "summary.json", "application/json")
            elif route == "/api/series":
                self._send_file(data_dir / "series.json", "application/json")
            elif route == "/healthz":
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": f"no such route: {route}"})

    return DashboardHandler


def make_server(host: str = "127.0.0.1", port: int = 8080,
                data_dir: Path = DEFAULT_DATA_DIR,
                static_dir: Path = STATIC_DIR) -> ThreadingHTTPServer:
    """Create (but do not start) the dashboard server. Port 0 = ephemeral."""
    return ThreadingHTTPServer((host, port), _make_handler(Path(data_dir), Path(static_dir)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--rebuild", action="store_true",
                        help="rebuild dashboard data from pipeline outputs first")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if args.rebuild or not (data_dir / "summary.json").is_file():
        print("building dashboard data from pipeline outputs ...")
        build_data.build_all(PROJECT_ROOT, data_dir)

    server = make_server(args.host, args.port, data_dir)
    print(f"SRE dashboard serving at http://{args.host}:{args.port}/  "
          f"(API: /api/summary, /api/series — Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
