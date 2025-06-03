#!/usr/bin/env bash
#
# This script builds and deploys the "fleet_analyzer" agent
# to Google Cloud Run, then exports the service URL.

# 1) Source common environment variables (PROJECT_ID, REGION, etc.)
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:18]{index=18}

# 2) Navigate to the directory containing the agent source and cloudbuild.yaml
cd ~/rousefleet-bootstrap/agents   ## :contentReference[oaicite:19]{index=19}

# 3) Define build/deploy variables
export IMAGE_TAG="latest"           ## :contentReference[oaicite:20]{index=20}
export AGENT_NAME="fleet_analyzer"  ## :contentReference[oaicite:21]{index=21}
export IMAGE_NAME="fleet-analyzer-agent"   ## :contentReference[oaicite:22]{index=22}
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"   ## :contentReference[oaicite:23]{index=23}
export SERVICE_NAME="fleet-analyzer-agent"   ## :contentReference[oaicite:24]{index=24}
export PUBLIC_URL="https://fleet-analyzer-agent-${PROJECT_NUMBER}.${REGION}.run.app"  ## :contentReference[oaicite:25]{index=25}

# 4) Build the Docker image and push to Artifact Registry
echo "Building ${AGENT_NAME} agent..."
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --substitutions=_AGENT_NAME="${AGENT_NAME}",_IMAGE_PATH="${IMAGE_PATH}"   ## :contentReference[oaicite:26]{index=26}

echo "Image built and pushed to: ${IMAGE_PATH}"

# 5) Deploy the container to Cloud Run, injecting necessary environment variables
echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_PATH}" \
  --platform=managed \
  --region="${REGION}" \
  --set-env-vars="SPANNER_INSTANCE_ID=${SPANNER_INSTANCE_ID}" \
  --set-env-vars="SPANNER_DATABASE_ID=${SPANNER_DATABASE_ID}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="A2A_HOST=0.0.0.0" \
  --set-env-vars="A2A_PORT=8080" \
  --set-env-vars="PUBLIC_URL=${PUBLIC_URL}" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" \
  --min-instances=1   ## :contentReference[oaicite:27]{index=27}

# 6) Retrieve and export the URL of the deployed service
export FLEET_ANALYZER_AGENT_URL="$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
    --filter="fleet-analyzer-agent"
)"   ## :contentReference[oaicite:28]{index=28}

echo "Deployed fleet-analyzer-agent at: ${FLEET_ANALYZER_AGENT_URL}"