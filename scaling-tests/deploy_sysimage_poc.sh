#!/usr/bin/env bash
# Deploy reopt-julia:sysimage (built in this branch) to Cloud Run as a third
# service for A/B comparison against the existing reopt-julia (bare) and
# reopt-julia-fast (off-tree sysimage).
#
# Shape mirrors reopt-julia-fast: minScale=1, containerConcurrency=1, gen2.
# That way the only variable between this and reopt-julia-fast is which
# sysimage build is on the container.
set -euo pipefail

PROJECT=bf-platform-dev-1
REGION=us-central1
SERVICE=reopt-julia-sysimage-poc
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/reopt/${SERVICE}:${TAG}"

echo "deploying $SERVICE -> $IMAGE"

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --platform=managed \
  --port=8081 \
  --command=julia \
  --args='--sysimage=/opt/julia_src/reopt_sysimage.so,--project=/opt/julia_src,-e,include("http.jl")' \
  --cpu=4 \
  --memory=8Gi \
  --timeout=900 \
  --concurrency=1 \
  --min-instances=1 \
  --max-instances=10 \
  --execution-environment=gen2 \
  --cpu-boost \
  --set-env-vars=XPRESS_JL_SKIP_LIB_CHECK=True,XPRESS_INSTALLED=False,JULIA_NUM_THREADS=4 \
  --set-secrets=NREL_DEVELOPER_API_KEY=reopt-nrel-api-key:latest \
  --allow-unauthenticated
