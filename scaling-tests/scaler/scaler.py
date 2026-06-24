"""
Queue-depth-driven replica scaler.

Each tick:
  1. Read Redis LLEN(queue) -> queue_depth
  2. Read backend.get_count() -> current
  3. desired = clamp(ceil(queue_depth / TARGET_PER_REPLICA), MIN_WARM, MAX)
  4. Apply asymmetric cooldown:
       - scale up: immediate
       - scale down: only if no scale-up in the last SCALE_DOWN_COOLDOWN_S
  5. If desired != current, backend.set_count(desired)

Config (env vars):
  REDIS_URL                 redis://redis:6379/0
  REDIS_QUEUE               celery
  MIN_WARM                  2
  MAX_REPLICAS              15
  TARGET_PER_REPLICA        5
  TICK_SECONDS              10
  SCALE_DOWN_COOLDOWN_S     60
  SCALER_BACKEND            mock | docker | nomad   (see backends.py)
"""
import logging
import math
import os
import time

import redis

import backends

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scaler")


def desired_count(queue_depth: int, *, min_warm: int, max_replicas: int,
                  target_per_replica: int) -> int:
    raw = math.ceil(queue_depth / target_per_replica) if queue_depth > 0 else 0
    return max(min_warm, min(max_replicas, raw))


def main():
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    queue = os.environ.get("REDIS_QUEUE", "celery")
    min_warm = int(os.environ.get("MIN_WARM", "2"))
    max_replicas = int(os.environ.get("MAX_REPLICAS", "15"))
    target = int(os.environ.get("TARGET_PER_REPLICA", "5"))
    tick = float(os.environ.get("TICK_SECONDS", "10"))
    cooldown = float(os.environ.get("SCALE_DOWN_COOLDOWN_S", "60"))

    r = redis.from_url(redis_url)
    backend = backends.from_env()

    log.info("scaler started: min=%d max=%d target=%d tick=%ss cooldown=%ss backend=%s",
             min_warm, max_replicas, target, tick, cooldown, type(backend).__name__)

    last_scale_up_at = 0.0

    while True:
        try:
            depth = r.llen(queue)
            current = backend.get_count()
            desired = desired_count(depth, min_warm=min_warm,
                                    max_replicas=max_replicas,
                                    target_per_replica=target)

            now = time.time()
            if desired > current:
                log.info("SCALE UP   depth=%d current=%d -> desired=%d", depth, current, desired)
                backend.set_count(desired)
                last_scale_up_at = now
            elif desired < current:
                since_up = now - last_scale_up_at
                if since_up < cooldown:
                    log.info("hold       depth=%d current=%d desired=%d (cooldown %.0fs<%.0fs)",
                             depth, current, desired, since_up, cooldown)
                else:
                    log.info("SCALE DOWN depth=%d current=%d -> desired=%d", depth, current, desired)
                    backend.set_count(desired)
            else:
                log.info("steady     depth=%d current=%d", depth, current)
        except Exception:
            log.exception("scaler tick failed; continuing")

        time.sleep(tick)


if __name__ == "__main__":
    main()
