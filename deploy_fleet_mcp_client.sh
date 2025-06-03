#!/usr/bin/env bash
#
# This script sets environment variables, builds the Docker image
# for “fleet_mcp_client,” pushes it, deploys to Cloud Run,
# and then exports the deployed service URL.

# 1) Load your common environment variables (PROJECT_ID, REGION, REPO_NAME, etc.)
. ~/rousefleet-bootstrap/set_env.sh

# 2) Change to the “agents” directory
cd ~/rousefleet-bootstrap/agents

# 3) Define image/tag/service names
export IMAGE_TAG="latest"
export AGENT_NAME="fleet_mcp_client"
export IMAGE_NAME="fleet_mcp_client-agent"
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# 4) Look up the MCP server’s URL (assumes “mcp-tool-server” is already deployed)
export MCP_SERVER_URL="$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
    | grep mcp-tool-server
)/sse"

# 5) Define Cloud Run service name & public URL
export SERVICE_NAME="fleet-mcp-client"
export PUBLIC_URL="https://fleet-mcp-client-${PROJECT_NUMBER}.${REGION}.run.app"

echo "Building ${AGENT_NAME} agent..."
gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --config=cloudbuild.yaml \
  --substitutions=_AGENT_NAME="${AGENT_NAME}",_IMAGE_PATH="${IMAGE_PATH}"

echo "Image built and pushed to: ${IMAGE_PATH}"

echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_PATH}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" \
  --set-env-vars="MCP_SERVER_URL=${MCP_SERVER_URL}" \
  --set-env-vars="A2A_HOST=0.0.0.0" \
  --set-env-vars="A2A_PORT=8080" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="PUBLIC_URL=${PUBLIC_URL}" \
  --min-instances=1

# 6) Capture the Cloud Run URL into an environment variable
export FLEET_AGENT_URL="$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
    | grep fleet-mcp-client
)"

echo "Deployed fleet-mcp-client at: ${FLEET_AGENT_URL}"