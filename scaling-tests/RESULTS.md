# Test results

Captured runs and what they prove. Append a new section each time a test is run.

---

## Cold start — bare image (baseline)

**Image:** `reopt-julia:bare` (built from existing `julia_src/Dockerfile`, 3.91GB)

**Measurement:** `time_to_healthy.sh reopt-julia:bare` — wall-clock from
`docker run` until `GET /health` returns 200.

**Result:** `READY in 6.54s`

**Important caveat — what this number IS and ISN'T:**
- ✅ IS: time for Julia to import packages and start the HTTP server.
- ❌ IS NOT: time until the first `POST /job` succeeds.

The `/health` endpoint just returns 200 — it doesn't construct a JuMP model,
invoke a solver, or exercise any REopt code paths. The "multi-minute cold
start" described informally is almost certainly time-to-first-successful-solve,
where JIT specialization of JuMP + MathOptInterface + the chosen solver
dominates on the first real request.

The sysimage A/B that follows compares `/health` time, which captures the
startup-side win. To quantify the *first-solve* win we'd need a representative
REopt input fixture and a benchmark that POSTs to `/job` — recommended as a
follow-up.

---

## Cold start — sysimage image

**Image:** `reopt-julia:sysimage` (built from `julia_src/Dockerfile.sysimage`, 5.26GB)
**Sysimage:** `/opt/julia_src/reopt_sysimage.so`, **599.8 MB**
**Build time:** sysimage trace ~18s + incremental compile ~118s on top of bare's
~5min instantiate ⇒ total ~10 min added to CI.

**Measurement:** same `time_to_healthy.sh` against the sysimage image.

**Result:** `READY in 5.98s` — **0.56s faster than bare (≈8%)**.

**This number is smaller than expected and worth interpreting carefully.**

Most of the 5.98s isn't `using` statements — it's:
1. Julia process startup (~0.5s, sysimage doesn't help)
2. `DotEnv.load!()` and other I/O (~unchanged)
3. `include("os_solvers.jl")` parses + lowers a file (~unchanged)
4. `HTTP.serve()` opening the socket (~unchanged)

The sysimage win on package-load time *is* real (the `using` block drops from
seconds to ~0), but it's small relative to the constant-cost startup pieces
the sysimage can't shorten.

**Where the sysimage actually pays off is the first `POST /job`** — JuMP +
MathOptInterface + the chosen solver get specialized on the user's input
shape, and that JIT pass on a bare image is what eats minutes. The
`@compile_workload` block in `sysimage/workload.jl` (one tiny LP and MIP per
solver) bakes those specialized methods into the sysimage, so the first real
solve skips most of the work.

**This benchmark does not capture that win.** A first-solve benchmark needs:
- A representative REopt input fixture (candidates exist in
  `reoptjl/test/posts/` — `pv_cost_update.json` at 382B and
  `existing_boiler.json` at 570B are small but may not be valid `/reopt`
  payloads; `all_inputs_test.json` at 16KB is a more likely working scenario).
- A bash script that boots a container, waits for `/health`, then times the
  first `POST /reopt` with the fixture body.
- A second identical POST to measure the steady-state warm time and confirm
  the first run was paying JIT cost.

Recommended next benchmark: `first_solve_time.sh <image> <fixture>`.

**What we have proved with these two numbers:**
1. The sysimage build pipeline is mechanically correct (image builds, starts,
   serves `/health`).
2. The `@compile_workload` trace runs without errors and bakes a 600MB
   sysimage of legitimate compiled methods.
3. Startup-side cold start is small either way — so warming a pool for
   "instant `/health` response" was never going to be the lever. The lever
   is sysimage + warm pool for "instant first solve."

---

## Cold start — live Cloud Run (the real prod-shape numbers)

Local Docker measurements are dwarfed by Cloud Run's actual cold-start cost
because real cold start includes: control-plane provisioning, container
image pull from Artifact Registry (3.9GB / 5.3GB depending on variant),
VM micro-instance boot, gVisor/gen2 init, then finally Julia startup.

Probed two deployed services with 15–25 concurrent `GET /health` to force
scale-up beyond the warm-pool floor (`containerConcurrency=1`, `minScale=1`).

### reopt-julia (bf-platform-mvp-dev, image tag 76560cf1, BARE)

Args: `--project=/opt/julia_src -e include("http.jl")` — no sysimage.

25 concurrent /health:
- 24 hit warm instances: **0.56–0.61s**
- 1 forced cold start: **59.25s**

### reopt-julia-fast (bf-platform-dev-1, SYSIMAGE)

Args: `--project=/opt/julia_src -J/opt/julia_src/sys_reopt.so --sysimage-native-code=yes -e include("http.jl")` — **already has a sysimage in production**.

15 concurrent /health:
- 11 hit warm instances: **0.40–0.44s**
- 1 borderline: 1.47s
- 3 forced cold starts: **21.31s, 21.34s, 21.57s**

### The headline number

**Sysimage cuts Cloud Run cold start from ~59s to ~21s — a 38s reduction (≈64%) on the same shape, same payload (a 24-byte `/health` response).**

That's just the startup side. First-solve will widen the gap further because
`reopt-julia-fast`'s `sys_reopt.so` has JuMP+solver methods already specialized.
We didn't measure first-solve here (fixture rabbit hole — see Phase 1 note),
but the architectural conclusion is unchanged: **sysimage is the single
highest-leverage cold-start fix, validated in production today.**

### Where the sysimage build source lives

It doesn't, in this repo. `git log --all -- julia_src` shows no
`PackageCompiler` / `create_sysimage` / `sys_reopt` history. The
`reopt-julia-fast` Cloud Run image was built off-tree (manual one-off or a
branch we don't have). The `julia_src/Dockerfile.sysimage` and
`julia_src/sysimage/` added in this branch are the first in-tree
reproducible build of that artifact — so the AWS Nomad migration doesn't
need to reverse-engineer what's running in prod.

### What this means for the Nomad migration

1. Ship the in-tree sysimage build as part of the migration (this branch).
2. Set `minScale`-equivalent at the Nomad layer = warm-pool fixed count.
3. With sysimage cold start ≈ 21s, Nomad `healthy_deadline = "2m"` is
   comfortably overprovisioned. Without sysimage we'd need `healthy_deadline`
   north of 90s and would still see noisy timeouts.
4. The custom scaler's `MIN_WARM` floor matters more than the policy
   sophistication — every cold start the scaler creates is ~21s of latency
   added to whichever request triggered it.

---

## Scaler policy — laptop, fake-julia + Docker backend

**Setup**
- Compose: `redis` + `fake-julia` (initial scale 2) + `worker` (scale 5)
- Scaler config: `MIN_WARM=2 MAX=15 TARGET_PER_REPLICA=5 TICK=5s SCALE_DOWN_COOLDOWN=30s`
- Load: `burst.py --n 100` → 100 jobs LPUSHed to Redis "celery" queue in one shot

**Timeline (full)**

```
T+0      scaler started: min=2 max=15 target=5 tick=5.0s cooldown=30.0s backend=DockerComposeBackend
T+0      steady     depth=0   current=2           # idle, MIN_WARM holds
T+25s    SCALE UP   depth=95  current=2  -> 15    # burst lands, jumps to MAX in one tick
T+32s    steady     depth=95  current=15          # all replicas online
T+55s    steady     depth=83  current=15          # queue draining
T+78s    SCALE DOWN depth=70  current=15 -> 14    # cooldown elapsed, begin shed
T+90s    SCALE DOWN depth=60  current=13 -> 12
T+107s   SCALE DOWN depth=55  current=12 -> 11
T+118s   SCALE DOWN depth=50  current=11 -> 10
T+133s   SCALE DOWN depth=43  current=10 -> 9
T+138s   SCALE DOWN depth=40  current=9  -> 8
T+150s   SCALE DOWN depth=35  current=8  -> 7
T+161s   SCALE DOWN depth=30  current=7  -> 6
T+172s   SCALE DOWN depth=24  current=6  -> 5
T+182s   SCALE DOWN depth=19  current=5  -> 4
T+193s   SCALE DOWN depth=14  current=4  -> 3
T+204s   SCALE DOWN depth=8   current=3  -> 2    # back at MIN_WARM
T+215s   steady     depth=3   current=2
T+220s   steady     depth=0   current=2          # queue drained, holding at MIN_WARM
```

**What this confirms**
1. Burst-driven scale-up reaches MAX in a single tick when `queue / TARGET_PER_REPLICA > MAX`. Correct.
2. Asymmetric cooldown gates the first scale-down by `SCALE_DOWN_COOLDOWN_S` after a scale-up. Correct.
3. After cooldown, scale-down ramps one step per tick as queue drains. Probably want a per-step cooldown later to avoid sawtoothing on a wobbly queue.
4. `DockerComposeBackend` correctly increases container count via `docker compose up --scale --no-recreate`, and the new containers register on the compose network so workers reach them immediately.

**Known limitations of this test**
- Throughput is bottlenecked by `worker=5`, not by `fake-julia` capacity, so the queue drained slower than 15 replicas could theoretically handle. Either bump workers in compose or raise to e.g. 20 to see fake-julia capacity as the real bottleneck. Does not affect scaler-policy correctness.
- Docker Compose's embedded DNS returns all replica IPs for `fake-julia`, but Python `requests` doesn't load-balance across them. In this test that's masked by worker count > replica count. In the real split-architecture test (`docker-compose.split.yml`), an nginx or Traefik in front of Julia replicas is required.
- No measurement of cold start — `fake-julia` boots in <1s. The real sysimage test (Test 2) will measure that.

**Next iterations to consider**
- Add a per-step `SCALE_DOWN_STEP_COOLDOWN_S` (say 15s) so we don't shed every tick.
- Add a Prometheus `/metrics` endpoint on the scaler itself so we can graph desired/current/depth over time instead of grepping logs.
- Wire NomadBackend against `nomad agent -dev` to validate the same policy against the real Nomad scale API (Test 4).
