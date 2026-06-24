#!/usr/bin/env bash
# Measure wall-clock time from container start until GET /health returns 200.
#
# This is the number that Nomad's health check measures in production, and it's
# the right metric for "cold start." It includes Julia startup, sysimage load,
# package init, and HTTP server boot.
#
# Usage:
#   time_to_healthy.sh <image>            # default port 8081, /health endpoint
#   time_to_healthy.sh <image> 8081 /health
#
# Example:
#   time_to_healthy.sh reopt-julia:bare
#   time_to_healthy.sh reopt-julia:sysimage
set -euo pipefail

IMAGE="${1:?usage: $0 <image> [port] [path]}"
PORT="${2:-8081}"
PATHQ="${3:-/health}"
NAME="ttoh-$(date +%s)-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "starting $IMAGE as $NAME ..."
START=$(date +%s.%N)
docker run -d --rm --name "$NAME" -p 0:"$PORT" "$IMAGE" >/dev/null
HOST_PORT=$(docker port "$NAME" "$PORT/tcp" | head -1 | cut -d: -f2)

echo "polling http://localhost:${HOST_PORT}${PATHQ} ..."
TIMEOUT=600  # 10 minutes max — fail loud if we exceed this
while true; do
    if curl -sf -o /dev/null "http://localhost:${HOST_PORT}${PATHQ}"; then
        END=$(date +%s.%N)
        ELAPSED=$(awk "BEGIN {printf \"%.2f\", $END - $START}")
        echo "READY in ${ELAPSED}s  image=${IMAGE}"
        exit 0
    fi
    NOW=$(date +%s.%N)
    SO_FAR=$(awk "BEGIN {printf \"%.0f\", $NOW - $START}")
    if [ "$SO_FAR" -gt "$TIMEOUT" ]; then
        echo "TIMEOUT after ${TIMEOUT}s waiting on ${PATHQ}"
        docker logs "$NAME" | tail -40
        exit 1
    fi
    sleep 0.5
done
