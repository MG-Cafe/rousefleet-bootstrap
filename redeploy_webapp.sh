#!/usr/bin/env bash
#
# This script builds and deploys the "rousefleet" web application
# to Google Cloud Run, exporting the resulting service under
# the name "rousefleet" and configuring required environment variables.

# 1) Load shared environment variables
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:0]{index=0}

# 2) Change into the application folder
cd ~/rousefleet-bootstrap/rousefleet/   ## :contentReference[oaicite:1]{index=1}

# 3) Define image/tag/service names
export IMAGE_TAG="latest"
export APP_FOLDER_NAME="rousefleet"
export IMAGE_NAME="rousefleet-webapp"
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"
export SERVICE_NAME="rousefleet"

# 4) Build the Docker image and push to Artifact Registry
echo "Building ${APP_FOLDER_NAME} webapp image..."
gcloud builds submit . \
  --tag="${IMAGE_PATH}" \
  --project="${PROJECT_ID}"   ## :contentReference[oaicite:2]{index=2}

# 5) Deploy the container to Cloud Run with environment variables, CPU, and memory
echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_PATH}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="SPANNER_INSTANCE_ID=${SPANNER_INSTANCE_ID}" \
  --set-env-vars="SPANNER_DATABASE_ID=${SPANNER_DATABASE_ID}" \
  --set-env-vars="APP_HOST=0.0.0.0" \
  --set-env-vars="APP_PORT=8080" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_API_KEY}" \
  --set-env-vars="FLEET_ORCHESTRATOR_AGENT_ID=${ORCHESTRATE_AGENT_ID}" \
  --project="${PROJECT_ID}" \
  --min-instances=1 \
  --cpu=2 \
  --memory=2Gi   ## :contentReference[oaicite:3]{index=3}

echo "Deployment complete: ${SERVICE_NAME} is now live."
