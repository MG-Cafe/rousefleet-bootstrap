#!/usr/bin/env bash
#
# build_and_deploy_rousefleet.sh
#
# 1) Source shared environment variables
# 2) Change into the rousefleet directory
# 3) Define IMAGE_TAG, IMAGE_NAME, IMAGE_PATH, and SERVICE_NAME
# 4) Build & push the Docker image to Artifact Registry
# 5) Deploy the container to Cloud Run with environment variables,
#    CPU, memory, and minimum instances.

# 1) Load shared env (PROJECT_ID, REGION, REPO_NAME, etc.)
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:28]{index=28}

# 2) Navigate into the rousefleet folder
cd ~/rousefleet-bootstrap/rousefleet/   ## :contentReference[oaicite:29]{index=29}

# 3) Define variables for building & deploying
export IMAGE_TAG="latest"                                         ## 
export APP_FOLDER_NAME="rousefleet"                              ## :contentReference[oaicite:31]{index=31}
export IMAGE_NAME="rousefleet-webapp"                            ## 
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"   ## 
export SERVICE_NAME="rousefleet"                                 ## 

# 4) Build & push the Docker image
echo "Building ${APP_FOLDER_NAME} webapp image..."
gcloud builds submit . \
  --tag="${IMAGE_PATH}" \
  --project="${PROJECT_ID}"   ## :contentReference[oaicite:35]{index=35}

# 5) Deploy the container to Cloud Run
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
  --memory=2Gi   ## :contentReference[oaicite:36]{index=36}

echo "✅ ${SERVICE_NAME} has been built and deployed to Cloud Run successfully."
