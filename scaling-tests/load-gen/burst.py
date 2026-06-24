"""
Push N jobs onto the Redis 'celery' queue all at once and watch the queue drain.

Used to validate the scaler reacts to bursty load.
"""
import argparse
import time

import redis


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=100, help="number of jobs to enqueue")
    p.add_argument("--redis-url", default="redis://localhost:6379/0")
    p.add_argument("--queue", default="celery")
    p.add_argument("--watch", action="store_true", help="poll queue depth until drained")
    args = p.parse_args()

    r = redis.from_url(args.redis_url)

    print(f"enqueueing {args.n} jobs to '{args.queue}' @ {args.redis_url}")
    pipe = r.pipeline()
    for i in range(args.n):
        pipe.lpush(args.queue, f"job-{i}")
    pipe.execute()

    if not args.watch:
        return

    t0 = time.time()
    while True:
        depth = r.llen(args.queue)
        print(f"t+{time.time() - t0:6.1f}s  queue_depth={depth}")
        if depth == 0:
            break
        time.sleep(2)
    print(f"queue drained in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
