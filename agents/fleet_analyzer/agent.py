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

#REPLACE FOR CheckCondition
class CheckCondition(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        log.info(f"FleetAnalyzer CheckCondition - Current summary_status: {ctx.session.state.get('summary_status', 'not set')}, Current summary: {str(ctx.session.state.get('summary', 'not set'))[:100]}")
        status = str(ctx.session.state.get("summary_status", "fail")).strip().lower()
        is_done = (status == "completed")
        yield Event(author=self.name, actions=EventActions(escalate=is_done))

#REPLACE FOR profile_agent
profile_agent = LlmAgent(
    name="equipment_profile_agent",
    model=MODEL_NAME,
    description="Agent to gather detailed information about a piece of fleet equipment using its ID or serial number.",
    instruction="""You are an agent that gathers detailed information about specific fleet equipment.
1. If a user provides a serial number (e.g., "SN123XYZ"), you MUST use the `get_equipment_id_by_serial` tool to find its unique equipment_id. If no ID is found, report that.
2. Once you have an equipment_id (either directly provided or found via serial number), you MUST use the `get_comprehensive_equipment_report` tool to fetch its details, current assignment, and recent maintenance history.
3. Your final output for this step should be the complete, structured report obtained from the `get_comprehensive_equipment_report` tool. If an error occurs fetching the report, output the error message.
Do not summarize or alter the report from the tool at this stage.
If the user asks a general question not about specific equipment, state that you need an equipment ID or serial number.
Example: User says "Tell me about SN123XYZ". You call `get_equipment_id_by_serial` with "SN123XYZ". If it returns "EQ789", you then call `get_comprehensive_equipment_report` with "EQ789" and output that report.
""",
    tools=[get_equipment_id_by_serial, get_comprehensive_equipment_report],
)

#REPLACE FOR summary_agent
summary_agent = LlmAgent(
    name="equipment_summary_agent",
    model=MODEL_NAME,
    description="Generates a concise, single-paragraph summary from a detailed equipment report.",
    instruction="""You will be given a detailed report about a piece of fleet equipment, which includes 'equipment_details' and 'recent_maintenance'.
Your task is to synthesize this information into a single, cohesive summary paragraph.
This summary should highlight:
- Key equipment specifications (make, model, year, category/subcategory).
- Current assignment (customer or service location, if available in the details).
- A brief note on recent maintenance activity (e.g., number of recent jobs, or "No recent maintenance found").
The paragraph should be informative and easy to read.
If the input report contains an error message, your summary should state that an error occurred while fetching details.
Your entire output must be this single summary paragraph.
""",
    output_key="summary"
)

#REPLACE FOR check_agent
check_agent = LlmAgent(
    name="summary_completion_check_agent",
    model=MODEL_NAME,
    description="Checks if a satisfactory summary for the requested equipment profile has been generated. Outputs 'completed' or 'pending'.",
    instruction="""Analyze the current state. You will see a 'summary' which is the output of the equipment_summary_agent.
If this 'summary' is present, is a non-empty string, and does not indicate an error in data retrieval (e.g., does not start with "Error:" or "No details found"), then the task is done. In this case, you MUST output the single word: completed
Otherwise, if there is no summary, or the summary indicates an error, or if processing is clearly still needed, you MUST output the single word: pending
""",
    output_key="summary_status"
)

#REPLACE FOR modify_output_after_agent
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

#REPLACE FOR root_agent
root_agent = LoopAgent(
    name="FleetAnalyzerWorkflowAgent",
    sub_agents=[
        profile_agent,
        summary_agent,
        check_agent,
        CheckCondition(name="WorkflowLoopChecker")
    ],
    description="Orchestrates agents to gather detailed information about fleet equipment and provide a summary.",
    max_iterations=3, 
    after_agent_callback=modify_output_after_agent
)

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