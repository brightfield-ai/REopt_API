"""
Drop-in stand-in for the real Julia HTTP solver during scaler-policy testing.

Mimics the real service's surface area:
  - GET  /health -> 200
  - POST /job    -> sleeps SOLVE_SECONDS (jittered) and returns {"ok": true}

Tracks in-flight count via a Prometheus-style /metrics endpoint so the scaler
(or a human watching) can see real-time load on this replica.
"""
import os
import random
import socket
import time
from contextlib import contextmanager
from threading import Lock

from fastapi import FastAPI

SOLVE_SECONDS = float(os.environ.get("SOLVE_SECONDS", "10"))
JITTER = float(os.environ.get("SOLVE_JITTER", "1"))
HOST = socket.gethostname()

app = FastAPI()

_lock = Lock()
_in_flight = 0
_total = 0


@contextmanager
def _track():
    global _in_flight, _total
    with _lock:
        _in_flight += 1
        _total += 1
    try:
        yield
    finally:
        with _lock:
            _in_flight -= 1


@app.get("/health")
def health():
    return {"status": "ok", "host": HOST}


@app.post("/job")
def solve():
    with _track():
        time.sleep(max(0.1, SOLVE_SECONDS + random.uniform(-JITTER, JITTER)))
    return {"ok": True, "host": HOST}


@app.get("/metrics")
def metrics():
    return {"in_flight": _in_flight, "total_solved": _total, "host": HOST}
