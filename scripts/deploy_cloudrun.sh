#!/usr/bin/env bash
#
# Deploy CereMind to Google Cloud Run, with the Cerebras API key stored in
# Secret Manager (never baked into the image or env files).
#
# Prereqs: gcloud CLI authenticated (`gcloud auth login`), billing enabled.
# Usage:
#   PROJECT_ID=my-proj REGION=us-central1 CEREBRAS_API_KEY=csk-... ./scripts/deploy_cloudrun.sh
#
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-ceremind}"
REPO="${REPO:-ceremind}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:latest"

echo ">> Using project=${PROJECT_ID} region=${REGION} service=${SERVICE}"
gcloud config set project "${PROJECT_ID}"

echo ">> Enabling required APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com

echo ">> Ensuring Artifact Registry repo exists"
gcloud artifacts repositories describe "${REPO}" --location="${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${REPO}" --repository-format=docker --location="${REGION}"

# --- Secret Manager: store the Cerebras API key ---
if [[ -n "${CEREBRAS_API_KEY:-}" ]]; then
  echo ">> Storing CEREBRAS_API_KEY in Secret Manager"
  if gcloud secrets describe cerebras-api-key >/dev/null 2>&1; then
    printf "%s" "${CEREBRAS_API_KEY}" | gcloud secrets versions add cerebras-api-key --data-file=-
  else
    printf "%s" "${CEREBRAS_API_KEY}" | gcloud secrets create cerebras-api-key --data-file=-
  fi
fi

echo ">> Building image with Cloud Build"
gcloud builds submit --tag "${IMAGE}" --file docker/Dockerfile .

echo ">> Deploying to Cloud Run"
DEPLOY_ARGS=(
  --image "${IMAGE}"
  --region "${REGION}"
  --platform managed
  --allow-unauthenticated
  --port 8080
  --memory 2Gi
  --cpu 2
  --min-instances 0
  --max-instances 4
  --set-env-vars "CEREBRAS_MODEL=gemma-4-31b,PIPELINE_BACKEND=mock,EMBEDDING_BACKEND=auto"
)
if gcloud secrets describe cerebras-api-key >/dev/null 2>&1; then
  DEPLOY_ARGS+=(--set-secrets "CEREBRAS_API_KEY=cerebras-api-key:latest")
fi

gcloud run deploy "${SERVICE}" "${DEPLOY_ARGS[@]}"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo ">> Deployed: ${URL}"

echo ">> Smoke test"
curl -fsS "${URL}/api/health" && echo
echo ">> Done. Open ${URL}"
