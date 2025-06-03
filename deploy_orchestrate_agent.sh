#!/usr/bin/env bash
#
# run_all_agents.sh
#
# 1) Change to the agents directory
# 2) Source shared environment variables
# 3) Activate Python virtual environment
# 4) Fetch each agent’s Cloud Run URL
# 5) Aggregate all URLs into REMOTE_AGENT_ADDRESSES
# 6) Deploy the Orchestrator Agent to Agent Engine

# 1) Navigate into the agents folder
cd ~/rousefleet-bootstrap/agents/   ## :contentReference[oaicite:9]{index=9}

# 2) Source the environment—loads PROJECT_ID, REGION, etc.
. ~/rousefleet-bootstrap/set_env.sh   ## :contentReference[oaicite:10]{index=10}

# 3) Activate the Python virtual environment
source ~/rousefleet-bootstrap/env/bin/activate   ## 

# 4a) Retrieve fleet-mcp-client URL
export FLEET_MPC_CLIENT_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep fleet-mcp-client
)   ## :contentReference[oaicite:12]{index=12}

# 4b) Retrieve market-researcher-agent URL
export MARKET_RESEARCH_AGENT_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep market-researcher-agent
)   ## :contentReference[oaicite:13]{index=13}

# 4c) Retrieve fleet-analyzer-agent URL
export FLEET_ANALYZER_URL=$(
  gcloud run services list \
    --platform=managed \
    --region=us-central1 \
    --format='value(URL)' \
  | grep fleet-analyzer-agent
)   ## :contentReference[oaicite:14]{index=14}

# 5) Combine all three agent URLs into one comma-separated variable
export REMOTE_AGENT_ADDRESSES="${MARKET_RESEARCH_AGENT_URL},${FLEET_MPC_CLIENT_URL},${FLEET_ANALYZER_URL}"   ## :contentReference[oaicite:15]{index=15}

echo "Aggregated remote agent addresses: ${REMOTE_AGENT_ADDRESSES}"

# 6) Launch the Orchestrator by running the Python module
python -m app.agent_engine_app \
  --set-env-vars "AGENT_BASE_URL=${REMOTE_AGENT_ADDRESSES}"   ## :contentReference[oaicite:16]{index=16}
