import vertexai
from vertexai import agent_engines


# Define your project and location
PROJECT_ID = "qwiklabs-gcp-04-483260c45940"
LOCATION = "us-central1"
AGENT_ENGINE_ID = "4740223325760913408"

# Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Construct the full resource name of the agent engine
agent_resource_name = "projects/543154480703/locations/us-central1/reasoningEngines/4740223325760913408"

# Create a remote agent instance
adk_app = agent_engines.AgentEngine(agent_resource_name)

# Define your prompt
prompt = "Hello, how can you assist me today?"

for event in adk_app.stream_query(
    user_id="212",
    message="Hello, how can you assist me today?",
):
  print(event)

