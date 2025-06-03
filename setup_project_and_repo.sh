#!/usr/bin/env bash
#
# setup_project_and_repo.sh
#
# 1) Retrieve and export core project variables
# 2) Identify the default Compute Engine service account
# 3) Define Spanner and Cloud environment variables
# 4) Grant all necessary IAM roles to the default service account
# 5) Create an Artifact Registry Docker repository

# 1) Get current project ID and project number
export PROJECT_ID=$(gcloud config get-value project)                         ## :contentReference[oaicite:28]{index=28}
export PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")   ## :contentReference[oaicite:29]{index=29}

# 2) Find the default Compute Engine service account
export SERVICE_ACCOUNT_NAME=$(gcloud compute project-info describe --format="value(defaultServiceAccount)")   ## :contentReference[oaicite:30]{index=30}

# 3) Define Spanner and Cloud environment variables
export SPANNER_INSTANCE_ID="rousefleet-graph-instance"                       ## :contentReference[oaicite:31]{index=31}
export SPANNER_DATABASE_ID="graphdb"                                         ## :contentReference[oaicite:32]{index=32}
export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"                                  ## :contentReference[oaicite:33]{index=33}
export GOOGLE_GENAI_USE_VERTEXAI=TRUE                                        ## :contentReference[oaicite:34]{index=34}
export GOOGLE_CLOUD_LOCATION="us-central1"                                   ## :contentReference[oaicite:35]{index=35}

# 4) Grant IAM permissions to the default service account
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/spanner.admin"                                             ## :contentReference[oaicite:36]{index=36}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/spanner.databaseUser"                                        ## :contentReference[oaicite:37]{index=37}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/artifactregistry.admin"                                      ## :contentReference[oaicite:38]{index=38}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/cloudbuild.builds.editor"                                    ## :contentReference[oaicite:39]{index=39}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/run.admin"                                                   ## :contentReference[oaicite:40]{index=40}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/iam.serviceAccountUser"                                      ## :contentReference[oaicite:41]{index=41}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/aiplatform.user"                                              ## :contentReference[oaicite:42]{index=42}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/logging.logWriter"                                            ## :contentReference[oaicite:43]{index=43}

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}" \
  --role="roles/logging.viewer"                                               ## :contentReference[oaicite:44]{index=44}

# 5) Create an Artifact Registry Docker repository
export REPO_NAME="rousefleet-repo"                                            ## :contentReference[oaicite:45]{index=45}

gcloud artifacts repositories create "${REPO_NAME}" \
  --repository-format=docker \
  --location=us-central1 \
  --description="Docker repository for Rouse workshop"                       ## :contentReference[oaicite:46]{index=46}

echo "✅ Project setup and Artifact Registry repository '${REPO_NAME}' created successfully."
