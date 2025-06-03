#!/usr/bin/env bash
#
# This script sets environment variables, builds the Docker image
# for the “market_researcher” agent, pushes it, and then deploys
# the Cloud Run service.

# Load common env (PROJECT_ID, REGION, REPO_NAME, etc.)
. ~/rousefleet-bootstrap/set_env.sh

cd ~/rousefleet-bootstrap/agents

export IMAGE_TAG="latest"
export AGENT_NAME="market_researcher"
export IMAGE_NAME="market-researcher-agent"
export IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"
export SERVICE_NAME="market-researcher-agent"
export PUBLIC_URL="https://market-researcher-agent-${PROJECT_NUMBER}.${REGION}.run.app"

echo "Building ${AGENT_NAME} agent..."
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --substitutions=_AGENT_NAME="${AGENT_NAME}",_IMAGE_PATH="${IMAGE_PATH}"

echo "Image built and pushed to: ${IMAGE_PATH}"

# Now deploy to Cloud Run:
echo "Deploying ${SERVICE_NAME} to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_PATH}" \
  --platform=managed \
  --region="${REGION}" \
  --set-env-vars="A2A_HOST=0.0.0.0" \
  --set-env-vars="A2A_PORT=8080" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="PUBLIC_URL=${PUBLIC_URL}" \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" \
  --min-instances=1

# Capture the URL of the newly deployed service into an env var
export MARKET_RESEARCHER_AGENT_URL=$(
  gcloud run services list \
    --platform=managed \
    --region="${REGION}" \
    --format="value(URL)" \
    | grep "${SERVICE_NAME}"
)

echo "Deployed at: ${MARKET_RESEARCHER_AGENT_URL}"
