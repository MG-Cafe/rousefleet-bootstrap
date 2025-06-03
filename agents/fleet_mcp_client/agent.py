import asyncio
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
import logging 
import os
import nest_asyncio

# Load environment variables from .env file in the parent directory
# Place this near the top, before using env vars like API keys
load_dotenv()
MCP_SERVER_URL=os.environ.get("MCP_SERVER_URL", "http://0.0.0.0:8080/sse")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
 
# --- Global variables ---
# Define them first, initialize as None
root_agent: LlmAgent | None = None
exit_stack: AsyncExitStack | None = None
#REPLACE ME - FETCH TOOLS

async def get_tools_async():
    print("Attempting to connect to MCP Filesystem server...")
    tools, exit_stack = await MCPToolset.from_server(
      connection_params=SseServerParams(url=MCP_SERVER_URL, headers={})
    )
    return tools, exit_stack

async def get_agent_async():
  """
  Asynchronously creates the MCP Toolset and the LlmAgent.

  Returns:
      tuple: (LlmAgent instance, AsyncExitStack instance for cleanup)
  """
  tools, exit_stack = await get_tools_async()
 
  root_agent = LlmAgent(
      model='gemini-2.0-flash',
      name='fleet_ops_agent',
      instruction="""
        You are an operations assistant for the Rouse FleetPro system.
        Your goal is to help users manage fleet equipment by logging maintenance requests or updating equipment locations using available tools.

        Available Tools:
        1. `log_maintenance_request`: Use this to log a new maintenance issue.
           - Required arguments: `equipment_serial_number` (string), `reported_by` (string, use "FleetOpsAgent" always and dont kas user), `issue_description` (string), `urgency` (string: "High", "Medium", or "Low").
        2. `update_equipment_location`: Use this to update an equipment's location.
           - Required arguments: `equipment_id` (string), `new_city` (string).
           - Optional arguments: `new_address` (string), `latitude` (float), `longitude` (float), `notes` (string).

        Latitude and longitude **must be numbers (not quoted strings)** when you build JSON.

        Process user requests:
        - Identify the user's intent: Are they reporting a maintenance issue or an equipment location change?
        - Extract all necessary arguments for the appropriate tool from the user's query.
        - If required arguments are missing, politely ask the user for the specific missing information. Do not guess extensively. For `reported_by` in maintenance requests, default to "FleetOpsAgent" and dont ask the user.
        - Before calling a tool, you can briefly confirm the action you are about to take (e.g., "Okay, I will log a maintenance request for equipment [ID]...").
        - After the tool call, report the outcome (success or error message from the tool) to the user.
        - Be concise and direct.

      """,
      tools=tools,
  )
  print("LlmAgent created.")

  return root_agent, exit_stack


async def initialize():
   """Initializes the global root_agent and exit_stack."""
   global root_agent, exit_stack
   if root_agent is None:
       log.info("Initializing agent...")
       root_agent, exit_stack = await get_agent_async()
       if root_agent:
           log.info("Agent initialized successfully.")
       else:
           log.error("Agent initialization failed.")
       
   else:
       log.info("Agent already initialized.")

def _cleanup_sync():
    """Synchronous wrapper to attempt async cleanup."""
    if exit_stack:
        log.info("Attempting to close MCP connection via atexit...")
        try:
            asyncio.run(exit_stack.aclose())
            log.info("MCP connection closed via atexit.")
        except Exception as e:
            log.error(f"Error during atexit cleanup: {e}", exc_info=True)


nest_asyncio.apply()

log.info("Running agent initialization at module level using asyncio.run()...")
try:
    asyncio.run(initialize())
    log.info("Module level asyncio.run(initialize()) completed.")
except RuntimeError as e:
    log.error(f"RuntimeError during module level initialization (likely nested loops): {e}", exc_info=True)
except Exception as e:
    log.error(f"Unexpected error during module level initialization: {e}", exc_info=True)