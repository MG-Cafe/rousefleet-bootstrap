from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill
from common.task_manager import AgentTaskManager
from fleet_analyzer.fleet_analyzer_agent import FleetAnalyzerAgent
import os
import logging
from dotenv import load_dotenv

load_dotenv()  

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
host=os.environ.get("A2A_HOST", "0.0.0.0")
port=int(os.environ.get("A2A_PORT",8080))
PUBLIC_URL=os.environ.get("PUBLIC_URL")


def main():
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="fleet_equipment_analyzer",
            name="Fleet Equipment Analyzer",
            description="""
            Analyzes a specific piece of fleet equipment using its equipment ID or serial number.
            It provides a comprehensive summary of the equipment's specifications, its current assignment (customer or service location), and a brief overview of recent maintenance history.
            """,
            tags=["rousefleet"],
            examples=["Tell me about equipment EQ001"],
        )
        agent_card = AgentCard(
            name="Fleet Equipment Analyzer Agent",
            description="""
            A specialized agent that connects to the Rouse FleetPro system to perform detailed analysis of fleet equipment.
            It can take a serial number or equipment ID and return a full profile summary.
            """,
            url=f"{PUBLIC_URL}",
            version="1.0.0",
            defaultInputModes=FleetAnalyzerAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=FleetAnalyzerAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=FleetAnalyzerAgent()),
            host=host,
            port=port,
        )
        logger.info(f"Attempting to start server with Agent Card: {agent_card.name}")
        logger.info(f"Server object created: {server}")

        server.start()
    except Exception as e:
        logger.error(f"An error occurred during A2A server startup: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    main()