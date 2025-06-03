import asyncio
import json
import uvicorn
import os
from dotenv import load_dotenv
from mcp import types as mcp_types 
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
from rousefleet import log_maintenance_request, update_equipment_location

load_dotenv()

APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("PORT", os.environ.get("APP_PORT", "8080")))


log_maint_tool = FunctionTool(log_maintenance_request)
update_loc_tool = FunctionTool(update_equipment_location)

available_tools = {
    log_maint_tool.name:  log_maint_tool,
    update_loc_tool.name: update_loc_tool,
}

app = Server("adk-tool-mcp-server")
sse = SseServerTransport("/messages/")

#REPLACE ME - LIST TOOLS

@app.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
  """MCP handler to list available tools."""
  # Convert the ADK tool's definition to MCP format
  mcp_tool_schema_log_maint = adk_to_mcp_tool_type(log_maint_tool)
  mcp_tool_schema_update_loc = adk_to_mcp_tool_type(update_loc_tool)
  print(f"MCP Server: Received list_tools request. \n MCP Server: Advertising tool: {mcp_tool_schema_log_maint.name} and {mcp_tool_schema_update_loc}")
  return [mcp_tool_schema_update_loc,mcp_tool_schema_log_maint]
  
#REPLACE ME - CALL TOOLS

@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
  """MCP handler to execute a tool call."""
  print(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

  # Look up the tool by name in our dictionary
  tool_to_call = available_tools.get(name)
  if tool_to_call:
    try:
      adk_response = await tool_to_call.run_async(
          args=arguments,
          tool_context=None,
      )
      print(f"MCP Server: ADK tool '{name}' executed successfully.")

      response_text = json.dumps(adk_response, indent=2)
      return [mcp_types.TextContent(type="text", text=response_text)]

    except Exception as e:
      print(f"MCP Server: Error executing ADK tool '{name}': {e}")
      # Creating a proper MCP error response might be more robust
      error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
      return [mcp_types.TextContent(type="text", text=error_text)]
  else:
      # Handle calls to unknown tools
      print(f"MCP Server: Tool '{name}' not found.")
      error_text = json.dumps({"error": f"Tool '{name}' not implemented."})
      return [mcp_types.TextContent(type="text", text=error_text)]

async def handle_sse(request):
  """Runs the MCP server over standard input/output."""
  # Use the stdio_server context manager from the MCP library
  async with sse.connect_sse(
    request.scope, request.receive, request._send
  ) as streams:
    await app.run(
        streams[0], streams[1], app.create_initialization_options()
    )

starlette_app = Starlette(
 debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)

if __name__ == "__main__":
    print("Launching MCP Server exposing ADK tools...")
    uvicorn.run(
        starlette_app,
        host=APP_HOST,
        port=APP_PORT,
        log_level="info"
    )
