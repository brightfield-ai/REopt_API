# The scaler service, talking to Nomad's HTTP API via NomadBackend.
#
# Build the scaler image first:
#   docker build -t scaler:latest scaling-tests/scaler/
#
# Submit:
#   nomad job run scaling-tests/nomad/scaler.nomad.hcl
#
# In `nomad agent -dev` the API is reachable from inside a container at
# host.docker.internal:4646. In a real Nomad cluster, point NOMAD_ADDR at the
# in-cluster ACL-protected endpoint and mount the scaler's token via Vault.
job "scaler" {
  datacenters = ["dc1"]
  type        = "service"

  group "scaler" {
    count = 1

    task "scaler" {
      driver = "docker"

      config {
        image = "scaler:latest"
      }

      env {
        # Backend
        SCALER_BACKEND = "nomad"
        SCALER_JOB_ID  = "fake-julia"
        NOMAD_ADDR     = "http://host.docker.internal:4646"

        # Redis queue source — assumes the redis.nomad.hcl job is running.
        # service.consul will resolve once Consul is wired up; the dev-mode
        # fallback is the static port from redis.nomad.hcl.
        REDIS_URL   = "redis://host.docker.internal:6379/0"
        REDIS_QUEUE = "celery"

        # Policy
        MIN_WARM              = "2"
        MAX_REPLICAS          = "15"
        TARGET_PER_REPLICA    = "5"
        TICK_SECONDS          = "5"
        SCALE_DOWN_COOLDOWN_S = "30"
      }

      resources {
        cpu    = 100
        memory = 64
      }
    }
  }
}
