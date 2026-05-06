#!/usr/bin/env python3
"""SwiftDeploy API Service - Stage 4b with Prometheus /metrics"""

import os, time, random, threading, json, sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

MODE       = os.environ.get("MODE", "stable")
VERSION    = os.environ.get("APP_VERSION", "1.0.0")
PORT       = int(os.environ.get("APP_PORT", "3000"))
START_TIME = time.time()

# Metrics
_lock = threading.Lock()
_req_counts = {}       # (method, path, status_code) -> int
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
_dur_buckets = {}      # (method, path, le) -> int
_dur_sum     = {}      # (method, path) -> float
_dur_count   = {}      # (method, path) -> int

def record(method, path, status, duration):
    key = (method, path, str(status))
    mp  = (method, path)
    with _lock:
        _req_counts[key] = _req_counts.get(key, 0) + 1
        _dur_sum[mp]     = _dur_sum.get(mp, 0.0) + duration
        _dur_count[mp]   = _dur_count.get(mp, 0) + 1
        for b in BUCKETS:
            bk = (method, path, str(b))
            _dur_buckets[bk] = _dur_buckets.get(bk, 0) + (1 if duration <= b else 0)
        _dur_buckets[(method, path, "+Inf")] = _dur_count[mp]

def build_metrics():
    out = []
    out += ["# HELP http_requests_total Total HTTP requests",
            "# TYPE http_requests_total counter"]
    with _lock:
        for (m, p, s), c in sorted(_req_counts.items()):
            out.append(f'http_requests_total{{method="{m}",path="{p}",status_code="{s}"}} {c}')

    out += ["# HELP http_request_duration_seconds Latency histogram",
            "# TYPE http_request_duration_seconds histogram"]
    with _lock:
        mps = sorted(set((m, p) for (m, p, _) in _dur_buckets))
        for (m, p) in mps:
            for b in BUCKETS:
                out.append(f'http_request_duration_seconds_bucket{{method="{m}",path="{p}",le="{b}"}} {_dur_buckets.get((m,p,str(b)),0)}')
            out.append(f'http_request_duration_seconds_bucket{{method="{m}",path="{p}",le="+Inf"}} {_dur_buckets.get((m,p,"+Inf"),0)}')
            out.append(f'http_request_duration_seconds_sum{{method="{m}",path="{p}"}} {_dur_sum.get((m,p),0):.6f}')
            out.append(f'http_request_duration_seconds_count{{method="{m}",path="{p}"}} {_dur_count.get((m,p),0)}')

    out += ["# HELP app_uptime_seconds Uptime in seconds",
            "# TYPE app_uptime_seconds gauge",
            f"app_uptime_seconds {time.time()-START_TIME:.2f}",
            "# HELP app_mode 0=stable 1=canary",
            "# TYPE app_mode gauge",
            f"app_mode {1 if MODE=='canary' else 0}",
            "# HELP chaos_active 0=none 1=slow 2=error",
            "# TYPE chaos_active gauge"]
    with chaos_lock:
        cm = chaos_state.get("mode")
        out.append(f"chaos_active {0 if cm is None else (1 if cm=='slow' else 2)}")
    return "\n".join(out) + "\n"

# Chaos
chaos_state = {"mode": None, "duration": None, "rate": None}
chaos_lock  = threading.Lock()

def apply_chaos():
    with chaos_lock:
        m = chaos_state.get("mode")
        if m == "slow":   return False, chaos_state.get("duration", 0)
        if m == "error" and random.random() < chaos_state.get("rate", 0): return True, 0
    return False, 0

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply_json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Deployed-By", "swiftdeploy")
        if MODE == "canary": self.send_header("X-Mode", "canary")
        self.end_headers()
        self.wfile.write(data)

    def dispatch(self):
        t0 = time.time()
        m, p, s = self.command, self.path.split("?")[0], 200
        try:
            if   m=="GET"  and p=="/":        s = self.h_root()
            elif m=="GET"  and p=="/healthz":  s = self.h_healthz()
            elif m=="GET"  and p=="/metrics":  s = self.h_metrics()
            elif m=="POST" and p=="/chaos":    s = self.h_chaos()
            else: self.reply_json(404, {"error":"not found"}); s=404
        except Exception as e:
            self.reply_json(500, {"error": str(e)}); s=500
        finally:
            record(m, p, s, time.time()-t0)

    do_GET = do_POST = dispatch

    def h_root(self):
        err, delay = apply_chaos()
        if delay: time.sleep(delay)
        if err:
            self.reply_json(500, {"error":"chaos error"}); return 500
        self.reply_json(200, {"message": f"SwiftDeploy API -- {MODE} mode",
                              "mode": MODE, "version": VERSION,
                              "timestamp": datetime.now(timezone.utc).isoformat()})
        return 200

    def h_healthz(self):
        self.reply_json(200, {"status":"ok",
                              "uptime_seconds": round(time.time()-START_TIME, 2),
                              "mode": MODE, "version": VERSION})
        return 200

    def h_metrics(self):
        body = build_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return 200

    def h_chaos(self):
        if MODE != "canary":
            self.reply_json(403, {"error":"canary only"}); return 403
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
        except Exception:
            self.reply_json(400, {"error":"bad json"}); return 400
        mode = body.get("mode")
        with chaos_lock:
            if   mode=="slow":    chaos_state.update({"mode":"slow",  "duration":body.get("duration",2), "rate":None})
            elif mode=="error":   chaos_state.update({"mode":"error", "rate":body.get("rate",0.5),      "duration":None})
            elif mode=="recover": chaos_state.update({"mode":None,    "duration":None,                  "rate":None})
            else: self.reply_json(400,{"error":"unknown mode"}); return 400
        self.reply_json(200, {"status":"chaos applied","chaos":dict(chaos_state)})
        return 200

if __name__ == "__main__":
    print(f"[swiftdeploy] API mode={MODE} version={VERSION} port={PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
