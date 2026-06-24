# Test results

Captured runs and what they prove. Append a new section each time a test is run.

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
