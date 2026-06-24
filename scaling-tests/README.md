# scaling-tests

Local validation harness for the proposed Julia-on-Nomad architecture:
two Nomad jobs (Celery workers + Julia HTTP solver) scaled independently by
a custom scaler that reads Redis queue depth and calls Nomad's scale API.

These tests do **not** ship to production. They exist to:

1. Prove the scaler policy is correct under bursty load.
2. Quantify Julia cold-start time, with and without a PackageCompiler sysimage.
3. Validate the architectural split end-to-end before touching Voltus's Nomad cluster.

## Layout

| Path | Purpose |
|---|---|
| `fake-julia/` | FastAPI stub that `sleep(10)`s and returns success — drop-in for real Julia during scaler-policy testing. |
| `scaler/` | Scaler service. Polls Redis `LLEN`, computes desired replica count, calls a pluggable backend (Docker Compose, Nomad, Mock). |
| `load-gen/` | Burst load generator. Submits N concurrent jobs to Redis and reports latency distribution. |
| `compose/` | Docker Compose files for local-laptop tests (no Nomad required). |
| `nomad/` | Nomad jobspecs for `nomad agent -dev` integration tests. |
| `benchmarks/` | Cold-start benchmark scripts (used to validate the sysimage win). |

## Tests, fastest to slowest

### 1. Scaler policy (fake Julia, Docker backend)

```bash
docker compose -f compose/docker-compose.scaler.yml up --build -d
python load-gen/burst.py --n 100 --concurrency 100
# watch in another terminal:
docker compose -f compose/docker-compose.scaler.yml logs -f scaler
```

Validates: queue spike → scaler ticks → replica count climbs → queue drains → cooldown → scale back to `MIN_WARM`.
No Julia build required. ~1 minute to first signal.

### 2. Cold-start time (real Julia, no scaler)

```bash
benchmarks/time_to_healthy.sh reopt-julia:bare
benchmarks/time_to_healthy.sh reopt-julia:sysimage
```

Validates: sysimage drops time-to-`/health=200` from minutes to seconds.

### 3. Split architecture (real Django + Celery + multiple Julia replicas)

```bash
docker compose -f compose/docker-compose.split.yml up --build -d
```

Validates: Celery routes through nginx to multiple Julia replicas with load distribution.

### 4. Nomad dev mode (real scaler ↔ real Nomad API)

```bash
nomad agent -dev -bind 0.0.0.0 &
nomad job run nomad/redis.nomad.hcl
nomad job run nomad/fake-julia.nomad.hcl
nomad job run nomad/scaler.nomad.hcl
python load-gen/burst.py --n 100
```

Validates: same scaler code path that ships to prod, against the real Nomad HTTP API.
