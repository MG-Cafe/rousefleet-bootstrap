from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill
from common.task_manager import AgentTaskManager
from market_researcher.market_researcher_agent import MarketResearcherAgent
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

host=os.environ.get("A2A_HOST", "localhost")
port=int(os.environ.get("A2A_PORT",10003))
PUBLIC_URL=os.environ.get("PUBLIC_URL")


def main():
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="equipment_market_research",
            name="Equipment Market Research Agent",
            description="""
            An AI agent designed to research and summarize market information for construction and fleet equipment, 
            focusing on aspects like pricing, demand, and trends.
            """,
            tags=["equipmet-market-research"],
            examples=["What are the average auction prices for 2019 Caterpillar 320F excavators in Texas?"],
        )
        agent_card = AgentCard(
            name="Equipment Market Research Agent",
            description="""
            An AI agent designed to research and summarize market information for construction and fleet equipment, 
            focusing on aspects like pricing, demand, and trends. It uses Google Search to gather relevant data.
            """,
            url=f"{PUBLIC_URL}",
            version="1.0.0",
            defaultInputModes=MarketResearcherAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=MarketResearcherAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=MarketResearcherAgent()),
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