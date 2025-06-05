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


  
#REPLACE ME - CALL TOOLS



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
