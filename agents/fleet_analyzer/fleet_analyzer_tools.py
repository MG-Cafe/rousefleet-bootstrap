import os
from dotenv import load_dotenv
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
import json

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types
from google.cloud.spanner_v1.database import Database as SpannerDatabase
from google.api_core import exceptions

# --- Environment Variable Loading and Debugging ---
print("fleet_analyzer_tools.py: Attempting to load .env file...")
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    # Load .env and ensure it overrides existing environment variables for this script's context
    # This is crucial if other scripts (like set_env.sh) set these globally in the shell
    # before adk web is launched.
    load_dotenv(dotenv_path=dotenv_path, override=True)
    print(f"Fleet Analyzer Tools: LOADED .env file from: {dotenv_path}")
    # Debug: Print values IMMEDIATELY after loading .env
    print(f"Fleet Analyzer Tools: POST .env - PROJECT_ID from os.environ: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")
    print(f"Fleet Analyzer Tools: POST .env - INSTANCE_ID from os.environ: {os.environ.get('SPANNER_INSTANCE_ID')}")
    print(f"Fleet Analyzer Tools: POST .env - DATABASE_ID from os.environ: {os.environ.get('SPANNER_DATABASE_ID')}")
else:
    print(f"Fleet Analyzer Tools: .env file NOT FOUND at {dotenv_path}. Will rely on globally set environment variables or defaults.")

# --- Spanner Configuration ---
# These will now reflect .env values if override=True worked, or global env vars, or then defaults.
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") # Must be set either globally or in .env
SPANNER_INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID", "rousefleet-graph-instance")
SPANNER_DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID", "graphdb")

db_instance: Optional[SpannerDatabase] = None
spanner_client: Optional[spanner.Client] = None

print(f"Fleet Analyzer Tools: FINAL Spanner Config to be used: PROJECT_ID='{PROJECT_ID}', INSTANCE_ID='{SPANNER_INSTANCE_ID}', DATABASE_ID='{SPANNER_DATABASE_ID}'")

if not PROJECT_ID:
    print("Fleet Analyzer Tools: CRITICAL ERROR - GOOGLE_CLOUD_PROJECT is not effectively set. Cannot initialize Spanner client.")
elif not SPANNER_INSTANCE_ID:
    print("Fleet Analyzer Tools: CRITICAL ERROR - SPANNER_INSTANCE_ID is not effectively set. Cannot initialize Spanner client.")
elif not SPANNER_DATABASE_ID:
    print("Fleet Analyzer Tools: CRITICAL ERROR - SPANNER_DATABASE_ID is not effectively set. Cannot initialize Spanner client.")
else:
    try:
        spanner_client = spanner.Client(project=PROJECT_ID)
        instance = spanner_client.instance(SPANNER_INSTANCE_ID) # Use the resolved variable
        db_instance = instance.database(SPANNER_DATABASE_ID)   # Use the resolved variable
        
        print(f"Fleet Analyzer Tools: Attempting to check existence of {db_instance.name}...")
        if not db_instance.exists():
            print(f"Fleet Analyzer Tools Error: Database '{SPANNER_DATABASE_ID}' does not exist in instance '{SPANNER_INSTANCE_ID}'. Please ensure it's created and names are correct in your .env file or environment.")
            db_instance = None
        else:
            print(f"Fleet Analyzer Tools: Successfully connected to Spanner: {db_instance.name}")
            
    except exceptions.NotFound as nf_error:
        print(f"Fleet Analyzer Tools Error: Spanner resource not found. This usually means the INSTANCE_ID ('{SPANNER_INSTANCE_ID}') is incorrect for PROJECT_ID ('{PROJECT_ID}'), or less commonly the DATABASE_ID ('{SPANNER_DATABASE_ID}') if the instance was found. Error: {nf_error}")
        db_instance = None
    except Exception as e:
        print(f"Fleet Analyzer Tools Error: An unexpected error occurred during Spanner initialization: {e}")
        traceback.print_exc()
        db_instance = None

# --- The rest of your functions (run_sql_query, get_equipment_id_by_serial, etc.) remain unchanged from the previous version ---
# Ensure they all start with 'if not db_instance: ... return None'

def run_sql_query(sql: str, params: Optional[Dict[str, Any]] = None, param_types_map: Optional[Dict[str, Any]] = None, expected_fields: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
    if not db_instance:
        print("Fleet Analyzer Tools: run_sql_query - Database connection (db_instance) is not available.")
        return None 

    results_list: List[Dict[str, Any]] = []
    try:
        with db_instance.snapshot() as snapshot:
            results = snapshot.execute_sql(sql, params=params, param_types=param_types_map)
            
            actual_field_names = expected_fields
            if not actual_field_names:
                if results and hasattr(results, 'fields') and results.fields:
                    actual_field_names = [field.name for field in results.fields]
                else:
                    return [] 
            
            if not actual_field_names:
                 return []

            for row_idx, row in enumerate(results):
                if len(actual_field_names) != len(row):
                     print(f"Fleet Analyzer Tools: run_sql_query - Warning: Mismatch field names ({len(actual_field_names)}) vs row values ({len(row)}). Row {row_idx}: {row}")
                     continue
                results_list.append(dict(zip(actual_field_names, row)))
    except Exception as e:
        print(f"Fleet Analyzer Tools: An error occurred during SQL query execution: {e}")
        traceback.print_exc()
        return None
    return results_list

def get_equipment_id_by_serial(serial_number: str) -> Optional[str]:
    if not db_instance:
        print(f"fleet_analyzer_tools.py: get_equipment_id_by_serial - db_instance not available for SN {serial_number}.")
        return None
    sql = "SELECT equipment_id FROM Equipment WHERE serial_number = @serial_number LIMIT 1"
    params = {"serial_number": serial_number}
    param_types_map = {"serial_number": param_types.STRING}
    fields = ["equipment_id"]
    results = run_sql_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    if results:
        return results[0]['equipment_id']
    print(f"Fleet Analyzer Tools: No equipment_id found for serial_number: {serial_number}")
    return None

def get_equipment_details_for_analyzer(equipment_id: str) -> Optional[Dict[str, Any]]:
    if not db_instance:
        print(f"fleet_analyzer_tools.py: get_equipment_details_for_analyzer - db_instance not available for EQ_ID {equipment_id}.")
        return None
    sql = """
        SELECT
            eq.equipment_id, eq.serial_number, eq.description,
            eq.meter_hours, eq.current_city, eq.current_state_province,
            eq.category, eq.subcategory, eq.make, eq.model, eq.model_year,
            c.customer_name AS current_customer_name,
            sl.name AS current_service_location_name
        FROM Equipment AS eq
        LEFT JOIN Customer AS c ON eq.current_customer_id = c.customer_id
        LEFT JOIN ServiceLocation AS sl ON eq.current_service_location_id = sl.location_id
        WHERE eq.equipment_id = @equipment_id
    """
    params = {"equipment_id": equipment_id}
    param_types_map = {"equipment_id": param_types.STRING}
    fields = [
        "equipment_id", "serial_number", "description",
        "meter_hours", "current_city", "current_state_province",
        "category", "subcategory", "make", "model", "model_year",
        "current_customer_name", "current_service_location_name"
    ]
    results = run_sql_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    if results:
        return results[0]
    print(f"Fleet Analyzer Tools: No details found for equipment_id: {equipment_id}")
    return None

def get_recent_maintenance_for_equipment(equipment_id: str, limit: int = 3) -> Optional[List[Dict[str, Any]]]:
    if not db_instance:
        print(f"fleet_analyzer_tools.py: get_recent_maintenance_for_equipment - db_instance not available for EQ_ID {equipment_id}.")
        return None
    sql = """
        SELECT job_id, job_date, job_description, service_type, cost
        FROM MaintenanceJob
        WHERE equipment_id = @equipment_id
        ORDER BY job_date DESC
        LIMIT @limit
    """
    params = {"equipment_id": equipment_id, "limit": limit}
    param_types_map = {"equipment_id": param_types.STRING, "limit": param_types.INT64}
    fields = ["job_id", "job_date", "job_description", "service_type", "cost"]
    results = run_sql_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    if results is not None:
        for job in results:
            if isinstance(job.get('job_date'), datetime):
                job['job_date'] = job['job_date'].isoformat()
        return results
    print(f"Fleet Analyzer Tools: Error fetching maintenance for equipment_id: {equipment_id}")
    return None


def get_comprehensive_equipment_report(equipment_id: str) -> Optional[Dict[str, Any]]:
    if not db_instance:
        print(f"fleet_analyzer_tools.py: get_comprehensive_equipment_report - db_instance not available for EQ_ID {equipment_id}.")
        return {"error": "Database connection not available."} 
    if not equipment_id:
        return {"error": "Equipment ID is required to generate a comprehensive report."}
    
    print(f"fleet_analyzer_tools.py: get_comprehensive_equipment_report for ID: {equipment_id}")
    details = get_equipment_details_for_analyzer(equipment_id)
    
    if not details:
        return {"error": f"No primary details found for equipment ID: {equipment_id}"}
        
    maintenance_summary = get_recent_maintenance_for_equipment(equipment_id, limit=3)
    
    report = {
        "equipment_details": details,
        "recent_maintenance": maintenance_summary if maintenance_summary is not None else "Could not retrieve maintenance information.",
    }
    return report

def run_graph_query(graph_sql: str, params: Optional[Dict[str, Any]] = None, param_types_map: Optional[Dict[str, Any]] = None, expected_fields: Optional[List[str]] = None) -> Optional[List[Dict[str, Any]]]:
    if not db_instance:
        print("fleet_analyzer_tools.py: Database connection is not available for run_graph_query.")
        return None
    results_list: List[Dict[str, Any]] = []
    try:
        with db_instance.snapshot() as snapshot:
            results = snapshot.execute_sql(graph_sql, params=params, param_types=param_types_map)
            actual_field_names = expected_fields
            if not actual_field_names:
                if results and hasattr(results, 'fields') and results.fields:
                    actual_field_names = [field.name for field in results.fields]
                else: return []
            if not actual_field_names: return []
            for row in results:
                if len(actual_field_names) != len(row): continue
                results_list.append(dict(zip(actual_field_names, row)))
    except Exception as e:
        print(f"Fleet Analyzer Tools: An error occurred during Graph query execution: {e}")
        traceback.print_exc()
        return None
    return results_list