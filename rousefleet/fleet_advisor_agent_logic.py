import os
import json
import traceback
from dotenv import load_dotenv
from vertexai import agent_engines

load_dotenv()

AGENT_FULL_PATH = os.environ.get('FLEET_ORCHESTRATOR_AGENT_ID')
agent_engine_client = None

if AGENT_FULL_PATH:
    try:
        print(f"fleet_advisor_agent_logic: Initializing with full resource name: {AGENT_FULL_PATH}")
        agent_engine_client = agent_engines.AgentEngine(AGENT_FULL_PATH)
        print("fleet_advisor_agent_logic: Agent Engine client initialized successfully.")
    except Exception as e:
        print(f"fleet_advisor_agent_logic: ERROR - Failed to initialize Agent Engine client: {e}")
        traceback.print_exc()
        agent_engine_client = None
else:
    print("fleet_advisor_agent_logic: ERROR - Missing required environment variable: FLEET_ORCHESTRATOR_AGENT_ID")


def call_dispatch_agent_for_recommendation(job_date, job_location, equipment_category,
                                           equipment_make=None, duration_days=1,
                                           notes=None, requestor_name="User",
                                           user_id="dispatch_advisor_user_session"):
    # This function is correct and unchanged.
    global agent_engine_client
    if not agent_engine_client:
        yield {"type": "error", "data": {"message": "Fleet Orchestrator Agent client not initialized. Check server configuration and environment variables.", "code": "ORCHESTRATOR_CLIENT_INIT_FAIL"}}
        return

    try:
        from app import run_query
        from google.cloud.spanner_v1 import param_types
    except ImportError:
        yield {"type": "error", "data": {"message": "Internal Server Error: Could not import database utilities.", "code": "DB_IMPORT_ERROR"}}
        return

    yield {"type": "thought", "data": f"--- Finding best equipment candidate from database ---"}
    yield {"type": "thought", "data": f"Job Details: Date: {job_date}, Location: {job_location}, Category: {equipment_category}, Make: {equipment_make or 'Any'}"}

    initial_candidates = []
    try:
        sql = """
            SELECT equipment_id, serial_number, make, model, meter_hours, description
            FROM Equipment
            WHERE category = @category
              AND (@make IS NULL OR make = @make)
            ORDER BY meter_hours ASC
            LIMIT 1
        """
        params = {"category": equipment_category, "make": equipment_make if equipment_make else None}
        param_types_map = {"category": param_types.STRING, "make": param_types.STRING}
        expected_fields = ["equipment_id", "serial_number", "make", "model", "meter_hours", "description"]
        initial_candidates = run_query(sql, params, param_types_map, expected_fields)
        
        if not initial_candidates:
            yield {"type": "error", "data": {"message": "No suitable equipment candidates found in the database for the specified criteria.", "code": "NO_INITIAL_CANDIDATES_FOUND"}}
            return
            
        candidate_display_name = [f"{c.get('make')} {c.get('model')} (SN: {c.get('serial_number')})" for c in initial_candidates]
        yield {"type": "thought", "data": f"Found best candidate: {', '.join(candidate_display_name)}. Now sending to agent for analysis."}

    except Exception as db_query_exc:
        yield {"type": "error", "data": {"message": f"A database error occurred: {db_query_exc}", "code": "DB_QUERY_ERROR"}}
        return

    prompt_to_orchestrator = f"""
**Equipment Candidate to Analyze:**
- {initial_candidates[0].get('make')} {initial_candidates[0].get('model')} (ID: {initial_candidates[0].get('equipment_id')})

**Your Tasks:**
1. Generate a full, detailed status report for this specific piece of equipment.
2. Perform market research for this type of equipment ({equipment_category}) in the job's region ({job_location}).

Combine both reports into a single, easy-to-read textual response.
"""
    yield {"type": "thought", "data": "Sending prompt to Fleet Orchestrator Agent..."}

    accumulated_raw_output = ""
    try:
        stream = agent_engine_client.stream_query(user_id=user_id, message=prompt_to_orchestrator)
        for event in stream:
            event_as_string = str(event)
            yield {"type": "thought", "data": f"RAW AGENT EVENT: {event_as_string}"}
            accumulated_raw_output += event_as_string + "\n"
        
        final_agent_output = accumulated_raw_output.strip()
        
        if final_agent_output:
            response_payload = {
                "recommendation_text": final_agent_output,
                "recommended_equipment_id": initial_candidates[0].get('equipment_id'),
                "equipment_details": initial_candidates[0]
            }
            yield {"type": "recommendation_complete", "data": response_payload}
        else:
            yield {"type": "error", "data": {"message": "Orchestrator agent did not provide a final recommendation response.", "raw_output": "No textual output from orchestrator."}}

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"fleet_advisor_agent_logic: Error calling remote Orchestrator (recommendation): {e}\n{error_details}")
        yield {"type": "error", "data": {"message": f"Error interacting with Orchestrator Agent: {str(e)}", "code": "ORCHESTRATOR_CALL_FAIL", "raw_output": error_details}}


def execute_dispatch_assignment(user_name, equipment_id, equipment_details, job_details, agent_session_user_id):
    global agent_engine_client
    if not agent_engine_client:
        yield {"type": "error", "data": {"message": "Fleet Orchestrator Agent client not initialized. Check configuration.", "code": "ORCHESTRATOR_CLIENT_INIT_FAIL_EXEC"}}
        return

    yield {"type": "thought", "data": f"--- Dispatch Advisor to Remote Orchestrator: Execution Call ---"}
    yield {"type": "thought", "data": f"User ID for this session with Orchestrator: {agent_session_user_id}"}
    
    serial_number = equipment_details.get('serial_number', 'N/A')

    prompt_to_orchestrator_for_execution = f"""
User '{user_name}' .Equipment ID '{equipment_id}'.
Original Job Details:
- Location: {job_details.get('location')}
- Notes: {job_details.get('notes', 'None')}

Your task is to:
1. Instruct your 'Fleet MCP Agent' to call the 'update_fleetpro_equipment_location' tool for Equipment ID '{equipment_id}'. Set its new_city to '{job_details.get('location', '')}'.
2. Instruct your 'Fleet MCP Agent' to call the 'log_fleetpro_maintenance_request' tool for Equipment with serial number '{serial_number}'. Log an item like: issue_description='Pre-dispatch checks completed. Ready for job.', urgency='low'.
3. Confirm all actions taken and their success or failure.

Provide a final summary of actions performed.
"""
    yield {"type": "thought", "data": f"Sending confirmation to remote Fleet Orchestrator Agent to execute dispatch for Equipment ID: {equipment_id}..."}

    try:
        stream = agent_engine_client.stream_query(
            user_id=agent_session_user_id, 
            message=prompt_to_orchestrator_for_execution
        )
        execution_summary = ""
        for event in stream:
            event_as_string = str(event)
            yield {"type": "dispatch_update", "data": {"status": "orchestrator_exec_update", "message": f"RAW AGENT EVENT: {event_as_string}"}}
            execution_summary += event_as_string + "\n"
            if getattr(event, 'is_final', False) or getattr(event, 'turn_complete', False) or getattr(event, 'done', False):
                break
        
        if execution_summary:
            yield {"type": "dispatch_complete", "data": {"success": True, "message": f"Orchestrator processed dispatch confirmation. Final Status from Orchestrator: {execution_summary.strip()}"}}
        else:
            yield {"type": "error", "data": {"message": "Orchestrator agent did not provide a confirmation for dispatch execution.", "raw_output": "No final message from orchestrator execution phase."}}
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"fleet_advisor_agent_logic: Error calling remote Orchestrator (execution): {e}\n{error_details}")
        yield {"type": "thought", "data": f"Error calling remote Orchestrator agent for dispatch execution: {e}"}
        yield {"type": "error", "data": {"message": f"Error interacting with Orchestrator Agent for execution: {str(e)}", "code": "ORCHESTRATOR_EXEC_FAIL", "raw_output": error_details}}