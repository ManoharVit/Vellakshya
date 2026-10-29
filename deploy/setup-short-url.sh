#!/usr/bin/env bash
# ==============================================================================
# Vellakshya v2.0 - Short & Simple URL Setup (Google Cloud & Firebase Hosting)
# Target Project: vellakshya-gcp (Project # 489012899784)
# ==============================================================================
set -euo pipefail

PROJECT_ID="vellakshya-gcp"
REGION="us-central1"
SERVICE_NAME="vellakshya"

echo "=== Vellakshya Short & Simple URL Provisioning ==="
echo "Project: ${PROJECT_ID}"

# 1. Enable Firebase Hosting API in GCP
echo "--> Enabling Firebase Hosting API in GCP project..."
gcloud services enable firebasehosting.googleapis.com --project "${PROJECT_ID}"

# 2. Deploy Firebase Hosting rewrite to Cloud Run
echo "--> Deploying short URL proxy via Firebase Hosting..."
if command -v firebase &> /dev/null; then
    firebase deploy --only hosting --project "${PROJECT_ID}"
else
    echo "Firebase CLI not found in local environment. Use Cloud Shell or run: npm install -g firebase-tools"
fi

echo ""
echo "=== Your Short & Clean URLs ==="
echo "1. Primary Clean URL:   https://${PROJECT_ID}.web.app"
echo "2. Secondary Clean URL: https://${PROJECT_ID}.firebaseapp.com"
echo "3. Direct Cloud Run:    https://vellakshya-xb7gehmo6q-uc.a.run.app"
echo ""
echo "To attach your own custom domain (e.g., pdf.yourdomain.com):"
echo "  gcloud beta run domain-mappings create --service ${SERVICE_NAME} --domain YOUR_DOMAIN --region ${REGION}"
