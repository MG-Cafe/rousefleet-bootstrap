from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from common.task_manager import AgentWithTaskManager
from fleet_mcp_client import agent

class FleetAgent(AgentWithTaskManager):
  """An agent that act as operations assistant for the Rouse FleetPro system."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "fleet_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
      return "Processing Rouse FleetPro system operation request..."

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for processing operations requests on the Rouse FleetPro system."""
    return agent.root_agent