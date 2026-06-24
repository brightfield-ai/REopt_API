# Redis for local Nomad dev-mode testing of the scaler.
# In prod, the real Celery Redis is used and this jobspec is not needed.
job "redis" {
  datacenters = ["dc1"]
  type        = "service"

  group "redis" {
    count = 1

    network {
      port "tcp" {
        static = 6379
        to     = 6379
      }
    }

    service {
      name = "redis"
      port = "tcp"

      check {
        type     = "tcp"
        interval = "5s"
        timeout  = "2s"
      }
    }

    task "redis" {
      driver = "docker"

      config {
        image = "redis:7-alpine"
        ports = ["tcp"]
      }

      resources {
        cpu    = 200
        memory = 128
      }
    }
  }
}
