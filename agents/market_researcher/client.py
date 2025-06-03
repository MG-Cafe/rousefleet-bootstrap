import asyncio
from dotenv import load_dotenv
from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService


from . import agent 
import asyncio

load_dotenv()
async def async_main():
    session_service = InMemorySessionService()
    artifacts_service = InMemoryArtifactService()

    # Create a new session for the interaction
    session = session_service.create_session(
        state={},
        app_name='market_research_app', 
        user_id='user_mr_client'      
    )

    # Define the user query for the market research agent
    query = "What are recent auction prices for John Deere 35G excavators in California?" 
    print(f"User Query: '{query}'")
    
    content = types.Content(role='user', parts=[types.Part(text=query)])

    root_agent_instance = agent.root_agent 

    # Configure the ADK Runner
    runner = Runner(
        app_name='market_research_app', 
        agent=root_agent_instance,
        artifact_service=artifacts_service, 
        session_service=session_service,
    )

    print("Running agent...")
    

    events_async = runner.run_async(
        session_id=session.id, 
        user_id=session.user_id, 
        new_message=content
    )

  
    async for event in events_async:
        print(f"Event received: {event}")


if __name__ == '__main__':
    try:
        asyncio.run(async_main())
    except Exception as e:
        print(f"An error occurred: {e}")
    