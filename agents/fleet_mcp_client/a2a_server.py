from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill
from common.task_manager import AgentTaskManager
from fleet_mcp_client.fleet_agent import FleetAgent

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

host=os.environ.get("A2A_HOST", "localhost")
port=int(os.environ.get("A2A_PORT",10002))
PUBLIC_URL=os.environ.get("PUBLIC_URL")


def main():
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="fleet_ops",
            name="Fleet Operations Agent",
            description="""
            This agent helps users manage fleet equipment by logging maintenance requests or updating equipment locations 
            using available tools within the Rouse FleetPro system.
            """,
            tags=["fleet-management-operations"],
            examples=[
                "Report a maintenance issue for serial number 12345, it's leaking hydraulic fluid, high urgency.",
                "Update the location of equipment ID 56789 to Dallas, TX, with address 123 Main St.",
            ],
        )
        agent_card = AgentCard(
           name="Fleet Operations Agent",
            description="""
            You are an operations assistant for the Rouse FleetPro system.
            Your goal is to help users manage fleet equipment by logging maintenance requests or updating equipment locations 
            using available tools.
            """,
            url=f"{PUBLIC_URL}",
            version="1.0.0",
            defaultInputModes=FleetAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=FleetAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=FleetAgent()),
            host=host,
            port=port,
        )
        server.start()
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)

if __name__ == "__main__":
    main()