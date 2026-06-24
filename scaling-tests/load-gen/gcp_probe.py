"""
Probe the deployed Cloud Run reopt-julia instance to measure cold-start and
first-solve latency under bursty load.

What it does
------------
1. Single GET /health  — measures container-boot + Julia-startup time on a
   cold instance (or near-zero on a warm one).
2. N concurrent POST /reopt with a real fixture payload — first solve on a
   cold instance pays JIT-specialization cost on top of solve time; warm-hit
   solves are baseline.

Reports per-request: cold|warm (heuristic), HTTP status, wall-clock seconds,
and the response.status field from REopt. Prints a summary table and the
min/median/max so the cold-vs-warm spread is obvious.

Cost note: each /reopt POST runs a real HiGHS solve on Cloud Run for up to
Settings.timeout_seconds (420s in the fixture). 5 concurrent = up to 5 * 4
CPU-minutes of Cloud Run compute. Don't run this in a tight loop.

Usage:
  python gcp_probe.py \\
      --url https://reopt-julia-XXX-uc.a.run.app \\
      --payload ../../reoptjl/test/posts/all_inputs_test.json \\
      --n 5
"""
import argparse
import concurrent.futures as cf
import json
import statistics
import sys
import time
from pathlib import Path

import requests


def health(url: str, timeout: float = 120) -> dict:
    t0 = time.time()
    try:
        r = requests.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return {"elapsed_s": time.time() - t0, "status": r.status_code, "body": r.text[:100]}
    except Exception as e:
        return {"elapsed_s": time.time() - t0, "status": "ERR", "body": str(e)[:120]}


def reopt_solve(url: str, payload: dict, idx: int, timeout: float = 600) -> dict:
    t0 = time.time()
    try:
        r = requests.post(f"{url.rstrip('/')}/reopt", json=payload, timeout=timeout)
        elapsed = time.time() - t0
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "idx": idx,
            "elapsed_s": elapsed,
            "http_status": r.status_code,
            "solve_status": (body.get("status") or "?")[:30] if isinstance(body, dict) else "?",
            "n_messages": len(body.get("messages", {})) if isinstance(body, dict) else 0,
        }
    except Exception as e:
        return {"idx": idx, "elapsed_s": time.time() - t0, "http_status": "ERR",
                "solve_status": str(e)[:60], "n_messages": 0}


def health_burst(url: str, n: int) -> list:
    """Fire n concurrent GET /health and return per-request timings."""
    t_start = time.time()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(lambda i=i: (i, time.time() - t_start, health(url)))
                for i in range(n)]
        out = [f.result() for f in cf.as_completed(futs)]
    return sorted(out, key=lambda x: x[1] + x[2]["elapsed_s"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Cloud Run base URL")
    p.add_argument("--mode", choices=["full", "health-burst"], default="full",
                   help="full = single /health + N concurrent /reopt POSTs; "
                        "health-burst = N concurrent /health only (no payload, cheap)")
    p.add_argument("--payload", type=Path, default=None,
                   help="JSON file with full REopt scenario (required for --mode=full)")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--skip-health", action="store_true")
    args = p.parse_args()

    if args.mode == "health-burst":
        print(f"Cloud Run base: {args.url}")
        print(f"─── {args.n} concurrent GET /health ───")
        rows = health_burst(args.url, args.n)
        print(f"  {'idx':>3} {'submit_t':>10} {'elapsed_s':>10} {'status':>6}  body")
        for idx, sub_t, h in rows:
            print(f"  {idx:>3} {sub_t:>10.3f} {h['elapsed_s']:>10.2f} {str(h['status']):>6}  {h['body']!r}")
        elapsed = [h["elapsed_s"] for _, _, h in rows if h["status"] == 200]
        if elapsed:
            print(f"\n  min={min(elapsed):.2f}s  median={statistics.median(elapsed):.2f}s  "
                  f"max={max(elapsed):.2f}s  spread={max(elapsed) - min(elapsed):.2f}s")
        return

    if not args.payload:
        sys.exit("--payload is required for --mode=full")
    payload = json.loads(args.payload.read_text())
    print(f"Cloud Run base: {args.url}")
    print(f"Payload: {args.payload} ({args.payload.stat().st_size:,} bytes)")
    print(f"Settings: solver={payload.get('Settings', {}).get('solver_name', '?')} "
          f"timeout={payload.get('Settings', {}).get('timeout_seconds', '?')}s "
          f"run_bau={payload.get('Settings', {}).get('run_bau', '?')}")
    print()

    # Phase 1: /health — captures cold start of the container itself.
    if not args.skip_health:
        print("─── Phase 1: GET /health (cold-or-warm container boot) ───")
        h = health(args.url)
        print(f"  /health: {h['elapsed_s']:7.2f}s  status={h['status']}  body={h['body']!r}")
        print()

    # Phase 2: concurrent /reopt POSTs.
    print(f"─── Phase 2: {args.n} concurrent POST /reopt (real solve) ───")
    t_start = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.n) as ex:
        results = list(ex.map(lambda i: reopt_solve(args.url, payload, i), range(args.n)))
    total = time.time() - t_start

    results.sort(key=lambda r: r["elapsed_s"])
    print(f"  {'idx':>3} {'elapsed_s':>10} {'http':>5} {'solve_status':30} {'msgs':>4}")
    for r in results:
        print(f"  {r['idx']:>3} {r['elapsed_s']:>10.2f} {str(r['http_status']):>5} "
              f"{r['solve_status']:30} {r['n_messages']:>4}")
    print()
    elapsed = [r["elapsed_s"] for r in results if isinstance(r["http_status"], int) and r["http_status"] == 200]
    if elapsed:
        print(f"  successful solves: {len(elapsed)}/{args.n}")
        print(f"  min={min(elapsed):.1f}s  median={statistics.median(elapsed):.1f}s  max={max(elapsed):.1f}s")
    print(f"  total wall-clock: {total:.1f}s")
    print(f"  cold-vs-warm spread (max-min): {max(elapsed) - min(elapsed):.1f}s" if len(elapsed) >= 2 else "")


if __name__ == "__main__":
    main()
