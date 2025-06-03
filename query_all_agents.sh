#!/usr/bin/env bash
#
# This script:
#   1. Sources common environment variables
#   2. Activates the Python virtualenv
#   3. Retrieves each Cloud Run agent’s public URL
#   4. CURLs each agent’s /agent-card endpoint and pipes through jq
#   5. Combines all three URLs into REMOTE_AGENT_ADDRESSES

# 1) Load common environment variables (PROJECT_ID, REGION, etc.)
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:19]{index=19}

# 2) Activate the Python virtual environment (if any Python-specific tooling is needed)
source ~/rousefleet-bootstrap/env/bin/activate   ## :contentReference[oaicite:20]{index=20}

# 3a) Get the URL for fleet-mcp-client
export FLEET_MPC_CLIENT_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep fleet-mcp-client
)   ## :contentReference[oaicite:21]{index=21}

# 3a-ii) Fetch /agent-card for fleet-mcp-client
curl "$FLEET_MPC_CLIENT_URL/agent-card" | jq   ## :contentReference[oaicite:22]{index=22}

# 3b) Get the URL for market-researcher-agent
export MARKET_RESEARCH_AGENT_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep market-researcher-agent
)   ## :contentReference[oaicite:23]{index=23}

# 3b-ii) Fetch /agent-card for market-researcher-agent
curl "$MARKET_RESEARCH_AGENT_URL/agent-card" | jq   ## :contentReference[oaicite:24]{index=24}

# 3c) Get the URL for fleet-analyzer-agent
export FLEET_ANALYZER_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep fleet-analyzer-agent
)   ## :contentReference[oaicite:25]{index=25}

# 3c-ii) Fetch /agent-card for fleet-analyzer-agent
curl "$FLEET_ANALYZER_URL/agent-card" | jq   ## :contentReference[oaicite:26]{index=26}

# 4) Combine all agent URLs into a single variable
export REMOTE_AGENT_ADDRESSES="${MARKET_RESEARCH_AGENT_URL},${FLEET_MPC_CLIENT_URL},${FLEET_ANALYZER_URL}"   ## :contentReference[oaicite:27]{index=27}

echo "All agent URLs: ${REMOTE_AGENT_ADDRESSES}"
cd  ~/rousefleet-bootstrap/agents
sed -i "s|^\(O\?GOOGLE_CLOUD_PROJECT\)=.*|GOOGLE_CLOUD_PROJECT=${PROJECT_ID}|" ~/rousefleet-bootstrap/agents/orchestrate/.env
sed -i "s|^\(O\?REMOTE_AGENT_ADDRESSES\)=.*|REMOTE_AGENT_ADDRESSES=${REMOTE_AGENT_ADDRESSES}|" ~/rousefleet-bootstrap/agents/orchestrate/.env

echo "Updated orchestrator .env with PROJECT_ID=${PROJECT_ID} and REMOTE_AGENT_ADDRESSES."