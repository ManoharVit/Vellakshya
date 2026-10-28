# Google Cloud Run Deployment & Cost-Control Checklist (Step 2)

This checklist provides the exact administrative steps for provisioning Google Cloud Run with strict cost caps and budget alerts.

> [!CAUTION]
> **Billing Safeguard:** Budget alerts only send notifications; they do not automatically terminate workloads. Ensure you know where the **Disable Billing** button is in Google Cloud Console (`Billing > Manage billing accounts > Account Management > Disable Billing`).

---

## 1. Project & Budget Alert Setup

1. **Select or Create GCP Project:**
   ```bash
   gcloud projects create vellakshya-prod --name="Vellakshya PDF Workstation"
   gcloud config set project vellakshya-prod
   ```

2. **Configure Billing Account:**
   - Link your project to an active billing account.
   - Upgrade from free trial to standard billing before day 90 to prevent sudden quota suspensions.

3. **Set $1.00 USD Budget Alert:**
   - Navigate to **Google Cloud Console > Billing > Budgets & alerts**.
   - Create a budget named `vellakshya-cost-ceiling`.
   - Set **Target amount:** `$1.00 USD`.
   - Set threshold rules: `50%` ($0.50), `90%` ($0.90), and `100%` ($1.00).
   - Configure email notifications to your billing administrator.

---

## 2. Service Enablement & Artifact Registry

1. **Enable Required Google Cloud APIs:**
   ```bash
   gcloud services enable \
     run.googleapis.com \
     artifactregistry.googleapis.com \
     cloudbuild.googleapis.com \
     iam.googleapis.com
   ```

2. **Artifact Registry Free Tier Notice:**
   - Google Cloud provides **0.5 GB / month** of free Artifact Registry storage.
   - Set up a cleanup policy or manually delete older container images to stay within the free tier:
   ```bash
   gcloud artifacts repositories create vellakshya-repo \
     --repository-format=docker \
     --location=us-central1 \
     --description="Vellakshya Production Container Images"
   ```

---

## 3. Dedicated Service Account & GitHub Secrets

1. **Create Least-Privilege Deployment Service Account:**
   ```bash
   gcloud iam service-accounts create vellakshya-deployer \
     --display-name="Vellakshya GitHub Actions Deployer"
   ```

2. **Grant Minimal IAM Roles:**
   ```bash
   PROJECT_ID="vellakshya-prod"
   SA_EMAIL="vellakshya-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

   # Cloud Run Admin
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:${SA_EMAIL}" \
     --role="roles/run.admin"

   # Service Account User (to act as the runtime service account)
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:${SA_EMAIL}" \
     --role="roles/iam.serviceAccountUser"

   # Artifact Registry Writer
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:${SA_EMAIL}" \
     --role="roles/artifactregistry.writer"
   ```

3. **Generate Key & Configure GitHub Secret:**
   ```bash
   gcloud iam service-accounts keys create sa-key.json \
     --iam-account=${SA_EMAIL}
   ```
   - Copy the contents of `sa-key.json`.
   - In GitHub repository (`ManoharVit/Vellakshya`): **Settings > Secrets and variables > Actions > New repository secret**.
   - Name: `GCP_SA_KEY`
   - Value: `<paste contents of sa-key.json>`
   - Delete `sa-key.json` from your local machine immediately after adding to GitHub secrets.

---

## 4. Cloud Run Runtime Specifications

The automated workflow (`.github/workflows/deploy-cloud-run.yml`) enforces the following parameters:

| Parameter | Value | Rationale |
| :--- | :--- | :--- |
| **Region** | `us-central1` | Includes free 1 GB North America egress tier |
| **Min Instances** | `0` | Scale-to-zero when idle (zero ongoing cost) |
| **Max Instances** | `1` | Strictly caps concurrency and eliminates unexpected billing spikes |
| **Memory** | `1 GiB` | Accommodates PyMuPDF binary memory allocations |
| **CPU** | `1` | Request-based CPU allocation (billed only during processing) |
| **Max Upload Cap** | `30 MiB` | Safely bounded below Cloud Run's 32 MiB HTTP/1 request threshold |
| **Ephemeral Storage** | Acknowledged | In-memory processing; state persisted in client browser or external DB |

---

## 5. Deployment Verification Checklist

Once deployed:
- [ ] Verify public HTTPS URL loads without SSL errors.
- [ ] Measure cold start latency ($< 5\text{ s}$ target).
- [ ] Execute an upload, rotate, and export round-trip with a sample PDF.
- [ ] Test a file over 30 MiB and verify clean rejection (`413 Payload Too Large`).
- [ ] Confirm no container memory OOM restarts in Cloud Logging.
