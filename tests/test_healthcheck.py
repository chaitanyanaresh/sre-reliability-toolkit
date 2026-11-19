"""Tests for the health monitor against a local fixture HTTP server."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from healthcheck.monitor import poll


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")

    def log_message(self, *args):  # keep test output clean
        pass


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_healthy_endpoint_is_up(server):
    summaries = poll([f"{server}/ok"], rounds=3)
    s = summaries[f"{server}/ok"]
    assert s.checks == 3
    assert s.successes == 3
    assert s.success_rate == 1.0
    assert s.up is True
    assert s.mean_latency_ms() >= 0.0


def test_failing_endpoint_is_down(server):
    summaries = poll([f"{server}/bad"], rounds=3)
    s = summaries[f"{server}/bad"]
    assert s.checks == 3
    assert s.successes == 0
    assert s.success_rate == 0.0
    assert s.up is False


def test_mixed_endpoints(server):
    summaries = poll([f"{server}/ok", f"{server}/bad"], rounds=2)
    assert summaries[f"{server}/ok"].up is True
    assert summaries[f"{server}/bad"].up is False
