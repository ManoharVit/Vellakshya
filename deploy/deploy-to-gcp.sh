#!/usr/bin/env bash
# ==============================================================================
# Vellakshya v2.0 - Google Cloud Run Production Deployment Script
# Target Project: vellakshya-gcp (Project # 489012899784)
# Region: us-central1
# ==============================================================================
set -euo pipefail

PROJECT_ID="vellakshya-gcp"
REGION="us-central1"
SERVICE_NAME="vellakshya"
VERSION="2.0.0"

echo "=== Vellakshya v${VERSION} GCP Cloud Run Deployment ==="
echo "Target Project: ${PROJECT_ID}"
echo "Target Region:  ${REGION}"

# 1. Set active GCP project
gcloud config set project "${PROJECT_ID}"

# 2. Enable required GCP APIs if not already active
echo "--> Enabling Cloud Run, Cloud Build, Artifact Registry, and Secret Manager..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    compute.googleapis.com \
    --project "${PROJECT_ID}"

# 3. Deploy API Service to Cloud Run directly from source
echo "--> Deploying Cloud Run service '${SERVICE_NAME}'..."
gcloud run deploy "${SERVICE_NAME}" \
    --project "${PROJECT_ID}" \
    --source . \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 4 \
    --concurrency 80 \
    --timeout 300s \
    --set-env-vars ENVIRONMENT=production,GCP_PROJECT_ID="${PROJECT_ID}",VERSION="${VERSION}"

# 4. Deploy Isolated Worker Pool (Cloud Run Worker Pools GA)
if [ -f "deploy/cloudrun-worker-pool.yaml" ]; then
    echo "--> Deploying Worker Pool (Cloud Run Worker Pools GA)..."
    gcloud beta run worker-pools replace deploy/cloudrun-worker-pool.yaml \
        --project "${PROJECT_ID}" \
        --region "${REGION}" || echo "Worker pool deployment skipped or pending."
fi

# 5. Deploy OCR GPU Job (Cloud Run GPU GA)
if [ -f "deploy/cloudrun-ocr-gpu-job.yaml" ]; then
    echo "--> Deploying OCR GPU Job (Cloud Run GPU GA)..."
    gcloud beta run jobs replace deploy/cloudrun-ocr-gpu-job.yaml \
        --project "${PROJECT_ID}" \
        --region "${REGION}" || echo "OCR GPU job deployment skipped or pending."
fi

echo ""
echo "=== Deployment to Google Cloud Platform Completed Successfully! ==="
gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format="value(status.url)"
