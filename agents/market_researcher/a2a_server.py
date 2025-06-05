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

#Replace_with_a2a
