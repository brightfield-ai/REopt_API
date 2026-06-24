"""
Mini Celery stand-in: BLPOP from Redis, POST to Julia, repeat.

Not a real Celery worker — just enough to drain the queue so the scaler sees
queue depth change in response to replica count.
"""
import logging
import os
import socket
import time

import redis
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(socket.gethostname())

r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
julia_url = os.environ.get("JULIA_URL", "http://fake-julia:8081/job")

log.info("worker up, draining queue=celery -> %s", julia_url)
while True:
    try:
        item = r.blpop("celery", timeout=5)
        if item is None:
            continue
        _, payload = item
        t0 = time.time()
        resp = requests.post(julia_url, json={"payload": payload.decode()}, timeout=60)
        log.info("solved in %.1fs status=%d on host=%s",
                 time.time() - t0, resp.status_code, resp.json().get("host", "?"))
    except Exception:
        log.exception("worker iter failed")
        time.sleep(1)
