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

# 1. Enable Firebase Management & Hosting APIs in GCP
echo "--> Enabling Firebase Management & Hosting APIs in GCP project..."
gcloud services enable \
    firebase.googleapis.com \
    firebasehosting.googleapis.com \
    --project "${PROJECT_ID}"

# 2. Add Firebase capabilities to the GCP project if not already present
echo "--> Linking Firebase to GCP project ${PROJECT_ID}..."
firebase projects:addfirebase "${PROJECT_ID}" 2>/dev/null || echo "Firebase already linked or initialized."

# 3. Create hosting site if not yet existing
echo "--> Ensuring hosting site '${PROJECT_ID}' exists..."
firebase hosting:sites:create "${PROJECT_ID}" --project "${PROJECT_ID}" 2>/dev/null || echo "Hosting site already registered."

# 4. Deploy Firebase Hosting rewrite to Cloud Run
echo "--> Deploying short URL proxy via Firebase Hosting..."
firebase deploy --only hosting --project "${PROJECT_ID}"

echo ""
echo "=== Your Short & Clean URLs ==="
echo "1. Primary Clean URL:   https://${PROJECT_ID}.web.app"
echo "2. Secondary Clean URL: https://${PROJECT_ID}.firebaseapp.com"
echo "3. Direct Cloud Run:    https://vellakshya-xb7gehmo6q-uc.a.run.app"
echo ""
echo "To attach your own custom domain (e.g., pdf.yourdomain.com):"
echo "  gcloud beta run domain-mappings create --service ${SERVICE_NAME} --domain YOUR_DOMAIN --region ${REGION}"
