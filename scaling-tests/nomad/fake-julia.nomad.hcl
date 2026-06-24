# Nomad jobspec for the fake-julia stub, sized for `nomad agent -dev`.
#
# Production analogue lives at scaling-tests/nomad/reopt-julia.example.hcl
# (the same shape, pointing at the sysimage-baked reopt-julia:sysimage image,
# constrained to the julia node pool, with healthy_deadline tuned to absorb
# the sysimage cold start).
#
# Build the fake-julia image first:
#   docker build -t fake-julia:latest scaling-tests/fake-julia/
#
# Then submit:
#   nomad job run scaling-tests/nomad/fake-julia.nomad.hcl
job "fake-julia" {
  datacenters = ["dc1"]
  type        = "service"

  # Match how Voltus runs production canary deploys. Slow healthy_deadline so
  # Julia's first specialization pass doesn't get killed by Nomad mid-warmup.
  update {
    min_healthy_time = "10s"
    healthy_deadline = "5m"
    canary           = 1
    auto_promote     = true
    auto_revert      = true
    max_parallel     = 1
  }

  group "fake-julia" {
    # Scaler will adjust this at runtime. Start at MIN_WARM.
    count = 2

    scaling {
      enabled = true
      min     = 2
      max     = 15
    }

    network {
      port "http" {
        to = 8081
      }
    }

    service {
      name = "fake-julia"
      port = "http"

      check {
        type     = "http"
        path     = "/health"
        interval = "5s"
        timeout  = "2s"
      }
    }

    task "fake-julia" {
      driver = "docker"

      config {
        image = "fake-julia:latest"
        ports = ["http"]
      }

      env {
        SOLVE_SECONDS = "10"
        SOLVE_JITTER  = "1"
      }

      resources {
        cpu    = 200
        memory = 256
      }
    }
  }
}
