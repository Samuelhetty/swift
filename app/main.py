#!/usr/bin/env python3
"""
SwiftDeploy API Service
Supports stable and canary modes via MODE env var.
"""

import os
import time
import random
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sys

MODE = os.environ.get("MODE", "stable")
VERSION = os.environ.get("APP_VERSION", "1.0.0")
PORT = int(os.environ.get("APP_PORT", "3000"))
START_TIME = time.time()

# Chaos state
chaos_state = {"mode": None, "duration": None, "rate": None}
chaos_lock = threading.Lock()


def get_uptime():
    return round(time.time() - START_TIME, 2)


def apply_chaos():
    """Apply active chaos and return (should_error, delay_seconds)."""
    with chaos_lock:
        m = chaos_state.get("mode")
        if m == "slow":
            return False, chaos_state.get("duration", 0)
        elif m == "error":
            rate = chaos_state.get("rate", 0)
            if random.random() < rate:
                return True, 0
        return False, 0


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging (nginx handles access logs)
        pass

    def send_json(self, code, body, extra_headers=None):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Deployed-By", "swiftdeploy")
        if MODE == "canary":
            self.send_header("X-Mode", "canary")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/":
            self.handle_root()
        elif self.path == "/healthz":
            self.handle_healthz()
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/chaos":
            self.handle_chaos()
        else:
            self.send_json(404, {"error": "Not found"})

    def handle_root(self):
        should_error, delay = apply_chaos()
        if delay > 0:
            time.sleep(delay)
        if should_error:
            self.send_json(500, {"error": "Chaos induced error", "code": 500})
            return

        now = datetime.now(timezone.utc).isoformat()
        self.send_json(200, {
            "message": f"Welcome to SwiftDeploy API -- running in {MODE} mode",
            "mode": MODE,
            "version": VERSION,
            "timestamp": now,
        })

    def handle_healthz(self):
        self.send_json(200, {
            "status": "ok",
            "uptime_seconds": get_uptime(),
            "mode": MODE,
            "version": VERSION,
        })

    def handle_chaos(self):
        if MODE != "canary":
            self.send_json(403, {"error": "Chaos endpoint only available in canary mode"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(content_length)
        try:
            body = json.loads(body_raw)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        mode = body.get("mode")
        with chaos_lock:
            if mode == "slow":
                chaos_state["mode"] = "slow"
                chaos_state["duration"] = body.get("duration", 2)
                chaos_state["rate"] = None
            elif mode == "error":
                chaos_state["mode"] = "error"
                chaos_state["rate"] = body.get("rate", 0.5)
                chaos_state["duration"] = None
            elif mode == "recover":
                chaos_state["mode"] = None
                chaos_state["duration"] = None
                chaos_state["rate"] = None
            else:
                self.send_json(400, {"error": "Unknown chaos mode"})
                return

        self.send_json(200, {"status": "chaos applied", "chaos": dict(chaos_state)})


if __name__ == "__main__":
    print(f"[swiftdeploy] Starting API service | mode={MODE} version={VERSION} port={PORT}", flush=True)
    server = HTTPServer(("0.0.0.0", PORT), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[swiftdeploy] Shutting down", flush=True)
        sys.exit(0)
