#!/usr/bin/env bash
#
# build_and_deploy_mcp_tool_server.sh
#
# This script:
#   1. Sources shared environment variables
#   2. Changes into the tools/rousefleet directory
#   3. Defines IMAGE_TAG, MCP_IMAGE_NAME, IMAGE_PATH, SERVICE_NAME, and ROUSEFLEET_BASE_URL
#   4. Builds and pushes a Docker image to Artifact Registry
#   5. Deploys the image to Cloud Run with session affinity and required env vars

# 1) Source the shared environment variables (PROJECT_ID, REGION, REPO_NAME, etc.)
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:0]{index=0}

# 2) Navigate to the mcp-tool-server folder under tools/rousefleet
cd ~/rousefleet-bootstrap/tools/rousefleet   ## :contentReference[oaicite:1]{index=1}

# 3) Define image/tag/service variables
export IMAGE_TAG="latest"                                           ## :contentReference[oaicite:2]{index=2}
export MCP_IMAGE_NAME="mcp-tool-server"                             ## :contentReference[oaicite:3]{index=3}
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${MCP_IMAGE_NAME}:${IMAGE_TAG}"   ## :contentReference[oaicite:4]{index=4}
export SERVICE_NAME="mcp-tool-server"                                ## :contentReference[oaicite:5]{index=5}

# 3a) Retrieve the existing Rousefleet service base URL and append /api
export ROUSEFLEET_BASE_URL="$(gcloud run services list \
  --platform=managed \
  --region=us-central1 \
  --format='value(URL)' \
  | grep rousefleet --max-count=1)/api"                               ## :contentReference[oaicite:6]{index=6}

# 4) Build & push the Docker image to Artifact Registry
echo "Building ${MCP_IMAGE_NAME} image..."
gcloud builds submit . \
  --tag="${IMAGE_PATH}" \
  --project="${PROJECT_ID}"                                          ## :contentReference[oaicite:7]{index=7}

# 5) Deploy the image to Cloud Run with session affinity and environment variables
echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_PATH}" \
  --session-affinity \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="ROUSEFLEET_BASE_URL=${ROUSEFLEET_BASE_URL}" \
  --set-env-vars="APP_HOST=0.0.0.0" \
  --set-env-vars="APP_PORT=8080" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --project="${PROJECT_ID}" \
  --min-instances=1                                                 ## :contentReference[oaicite:8]{index=8}

echo "✅ ${SERVICE_NAME} has been built and deployed successfully."
