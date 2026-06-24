#!/usr/bin/env bash
# Run the scaler on the host, pointed at the local docker-compose smoke-test stack.
# Requires the .venv created by `python3 -m venv ../.venv && pip install redis requests`.
set -euo pipefail

cd "$(dirname "$0")"

VENV="$(cd .. && pwd)/.venv"
COMPOSE_FILE="$(cd ../compose && pwd)/docker-compose.scaler.yml"

export PYTHONUNBUFFERED=1
export SCALER_BACKEND=docker
export SCALER_COMPOSE_FILE="$COMPOSE_FILE"
export SCALER_SERVICE=fake-julia
export REDIS_URL=redis://localhost:6379/0
export REDIS_QUEUE=celery
export MIN_WARM=2
export MAX_REPLICAS=15
export TARGET_PER_REPLICA=5
export TICK_SECONDS=5
export SCALE_DOWN_COOLDOWN_S=30

exec "$VENV/bin/python" scaler.py
