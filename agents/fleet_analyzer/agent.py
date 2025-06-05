import asyncio
from contextlib import AsyncExitStack
import logging
import os
from typing import AsyncGenerator, Optional, List, Dict, Any

from dotenv import load_dotenv
from google.adk.agents import BaseAgent, LlmAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext

try:
    from google.genai import types as gemini_types # For types.Content, if using google.genai directly
except ImportError:
    from mcp import types as gemini_types # Fallback or if ADK re-exports it via mcp

from .fleet_analyzer_tools import get_equipment_id_by_serial, get_comprehensive_equipment_report

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.0-flash" # Or your preferred available model


class CheckCondition(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        log.info(f"FleetAnalyzer CheckCondition - Current summary_status: {ctx.session.state.get('summary_status', 'not set')}, Current summary: {str(ctx.session.state.get('summary', 'not set'))[:100]}")
        status = str(ctx.session.state.get("summary_status", "fail")).strip().lower()
        is_done = (status == "completed")
        yield Event(author=self.name, actions=EventActions(escalate=is_done))

#REPLACE FOR fleet_analyzer_sub_agents



def modify_output_after_agent(callback_context: CallbackContext) -> Optional[gemini_types.Content]:
    agent_name = callback_context.agent_name
    invocation_id = callback_context.invocation_id
    current_state = callback_context.state.to_dict()
    log.info(f"[Callback] Exiting workflow agent: {agent_name} (Inv: {invocation_id})")
    log.info(f"[Callback] summary_status from state: {current_state.get('summary_status')}")
    
    status = str(current_state.get("summary_status", "")).strip().lower()
    is_done = (status == "completed")
    
    final_summary = current_state.get("summary")
    log.info(f"[Callback] Final summary from state: {final_summary}")

    if final_summary and is_done and isinstance(final_summary, str):
        log.info("[Callback] Workflow complete. Returning final summary.")
        return gemini_types.Content(role="model", parts=[gemini_types.Part(text=final_summary.strip())])
    
    profile_agent_output = current_state.get(profile_agent.name)
    if isinstance(profile_agent_output, dict) and profile_agent_output.get("error"):
        log.warning(f"[Callback] Profile agent reported an error: {profile_agent_output.get('error')}")
        return gemini_types.Content(role="model", parts=[gemini_types.Part(text=f"Error during profile generation: {profile_agent_output.get('error')}")])
        
    fallback_message = f"Processing status: {status}. Could not generate a final summary. Check agent logs."
    if isinstance(final_summary, str) and not is_done : # Partial summary but not marked completed
        fallback_message = f"Processing status: {status}. Partial result: {final_summary.strip()}"
    elif profile_agent_output:
        fallback_message = f"Processing status: {status}. Profile data was gathered but summarization may have failed. Raw profile output: {str(profile_agent_output)[:200]}..."
        
    log.warning(f"[Callback] Workflow did not complete successfully or summary was not adequate. Fallback: {fallback_message}")
    return gemini_types.Content(role="model", parts=[gemini_types.Part(text=fallback_message)])

#REPLACE FOR fleet_analyzer_root_agent


async def initialize():
   global root_agent 
   log.info("Fleet Analyzer Workflow Agent module loaded. Root agent is defined.")
   pass

try:
    import nest_asyncio
    nest_asyncio.apply()
except (ImportError, RuntimeError):
    log.info("nest_asyncio not applied or not needed for Fleet Analyzer Agent.")

if __name__ == '__main__':
    log.info("This is the Fleet Analyzer agent module. It should be run via ADK tools (e.g., adk web).")
else:
    pass
