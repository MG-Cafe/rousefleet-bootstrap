# db.py for Rouse FleetPro (Spanner Graph Query Examples)

import os
import traceback
from datetime import datetime # Keep for potential date handling in results
import json # For example usage printing

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types
from google.api_core import exceptions

# --- Spanner Configuration for FleetPro ---
# Ensure these match your FleetPro Spanner setup
INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID", "rousefleet-graph-instance")
DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID", "graphdb") # This was 'graphdb' in your setup
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    print("Warning: GOOGLE_CLOUD_PROJECT environment variable not set in db.py. Spanner connection will fail.")

# --- Spanner Client Initialization ---
db = None # This will be the database object
spanner_client = None
try:
    if PROJECT_ID:
        spanner_client = spanner.Client(project=PROJECT_ID)
        instance = spanner_client.instance(INSTANCE_ID)
        database = instance.database(DATABASE_ID)
        print(f"db.py: Attempting to connect to Spanner: {instance.name}/databases/{database.name}")

        if not database.exists():
             print(f"db.py: Error - Database '{database.name}' does not exist in instance '{instance.name}'.")
             print(f"db.py: Please ensure the database and FleetGraph schema are created.")
             db = None
        else:
            print("db.py: Spanner database connection check successful.")
            db = database # Assign the database object
    else:
        print("db.py: Skipping Spanner client initialization due to missing GOOGLE_CLOUD_PROJECT.")

except exceptions.NotFound:
    print(f"db.py: Error - Spanner instance '{INSTANCE_ID}' not found in project '{PROJECT_ID}'.")
    db = None
except Exception as e:
    print(f"db.py: An unexpected error occurred during Spanner initialization: {e}")
    traceback.print_exc()
    db = None

# --- Utility Function (Graph Query Specific) ---

def run_graph_query(db_instance, graph_sql, params=None, param_types_map=None, expected_fields=None):
    """
    Executes a Spanner Graph Query (GQL).

    Args:
        db_instance: The Spanner database object.
        graph_sql (str): The GQL query string (starting with 'Graph ...').
        params (dict, optional): Dictionary of query parameters.
        param_types_map (dict, optional): Dictionary mapping param names to Spanner types.
        expected_fields (list[str], optional): Expected column names in order. Essential for GQL.

    Returns:
        list[dict]: A list of dictionaries representing the rows, or None on error.
    """
    if not db_instance:
        print("db.py - run_graph_query: Error - Database connection is not available.")
        return None

    results_list = []
    print(f"--- db.py: Executing Graph Query ---")
    # print(f"GQL: {graph_sql}") # Uncomment for verbose query logging
    # if params: print(f"Params: {params}")

    if not expected_fields:
        print("db.py - run_graph_query: Error - 'expected_fields' must be provided for graph queries.")
        return None

    try:
        with db_instance.snapshot() as snapshot:
            results = snapshot.execute_sql(
                graph_sql,
                params=params,
                param_types=param_types_map
            )
            for row in results:
                if len(expected_fields) != len(row):
                     print(f"db.py - run_graph_query: Warning - Mismatch between field names ({len(expected_fields)}) and row values ({len(row)}). Skipping row: {row}")
                     continue
                results_list.append(dict(zip(expected_fields, row)))
            # print(f"db.py - run_graph_query: Successful, fetched {len(results_list)} rows.")
    except (exceptions.NotFound, exceptions.PermissionDenied, exceptions.InvalidArgument) as spanner_err:
        print(f"db.py - run_graph_query: Spanner Graph Query Error ({type(spanner_err).__name__}): {spanner_err}")
        return None # Return None to indicate a query failure
    except Exception as e:
        print(f"db.py - run_graph_query: An unexpected error occurred: {e}")
        traceback.print_exc()
        return None

    return results_list


# --- FleetPro Graph Data Fetching Functions ---

def get_equipment_with_customers_graph(db_instance, limit=20):
    """
    Fetches equipment and their operating customers using FleetGraph.
    """
    if not db_instance: return None
    graph_sql = """
        Graph FleetGraph
        MATCH (eq:EquipmentNode)-[op:EquipmentOperatedBy]->(c:CustomerNode)
        RETURN eq.serial_number AS equipment_serial, eq.make AS equipment_make, eq.model AS equipment_model,
               c.customer_name AS customer_name, c.industry_type AS customer_industry
        ORDER BY c.customer_name, eq.make, eq.model
        LIMIT @limit
    """
    params = {"limit": limit}
    param_types_map = {"limit": param_types.INT64}
    fields = ["equipment_serial", "equipment_make", "equipment_model", "customer_name", "customer_industry"]
    return run_graph_query(db_instance, graph_sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_equipment_at_shared_location_graph(db_instance, location_name=None, limit=10):
    """
    Finds pairs of equipment at the same service location.
    Optionally filters by a specific location name.
    """
    if not db_instance: return None
    graph_sql = """
        Graph FleetGraph
        MATCH (eq1:EquipmentNode)-[:LocatedAtServiceDepot]->(sl:ServiceLocationNode)<-[:LocatedAtServiceDepot]-(eq2:EquipmentNode)
        WHERE eq1.equipment_id < eq2.equipment_id
          AND (@location_name_param IS NULL OR sl.name = @location_name_param)
        RETURN eq1.serial_number AS equipment1_sn, eq1.make AS equipment1_make,
               eq2.serial_number AS equipment2_sn, eq2.make AS equipment2_make,
               sl.name AS shared_location_name
        ORDER BY sl.name, equipment1_sn, equipment2_sn
        LIMIT @limit
    """
    params = {"location_name_param": location_name, "limit": limit}
    param_types_map = {"location_name_param": param_types.STRING, "limit": param_types.INT64}
    fields = ["equipment1_sn", "equipment1_make", "equipment2_sn", "equipment2_make", "shared_location_name"]
    return run_graph_query(db_instance, graph_sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_maintenance_for_customer_equipment_graph(db_instance, customer_name_filter, limit=20):
    """
    Multi-hop: Gets maintenance jobs for equipment operated by a specific customer.
    """
    if not db_instance: return None
    graph_sql = """
        Graph FleetGraph
        MATCH (cust:CustomerNode {customer_name: @customer_name_param})-[:OperatesEquipment]->(eq:EquipmentNode)<-[:PerformedOnEquipment]-(job:MaintenanceJobNode)
        RETURN cust.customer_name, eq.serial_number AS equipment_serial, eq.make AS equipment_make,
               job.job_id, job.job_description, job.service_type, job.job_date, job.cost
        ORDER BY eq.serial_number, job.job_date DESC
        LIMIT @limit
    """
    params = {"customer_name_param": customer_name_filter, "limit": limit}
    param_types_map = {"customer_name_param": param_types.STRING, "limit": param_types.INT64}
    fields = ["customer_name", "equipment_serial", "equipment_make", "job_id", "job_description", "service_type", "job_date", "cost"]
    
    results = run_graph_query(db_instance, graph_sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    if results: # Convert datetime objects for easier JSON serialization if needed
        for row in results:
            if isinstance(row.get('job_date'), datetime):
                row['job_date'] = row['job_date'].isoformat()
    return results


# --- Example Usage (if run directly) ---
if __name__ == "__main__":
    if db: # Check if db object was successfully initialized
        print("\n--- db.py: Testing FleetPro Graph Data Fetching Functions ---")

        print("\n1. Fetching Equipment with their Operating Customers (Graph Query)")
        equipment_customers = get_equipment_with_customers_graph(db, limit=5)
        if equipment_customers is not None:
            print(json.dumps(equipment_customers, indent=2))
        else:
            print("Failed to fetch equipment with customers.")

        # Example: Replace "Toronto Central Depot" with an actual service location name from your data
        test_location_name = "Toronto Central Depot"
        print(f"\n2. Fetching Equipment at Shared Location: {test_location_name} (Graph Query)")
        shared_location_equipment = get_equipment_at_shared_location_graph(db, location_name=test_location_name, limit=5)
        if shared_location_equipment is not None:
            print(json.dumps(shared_location_equipment, indent=2))
        else:
            print(f"Failed to fetch equipment at shared location '{test_location_name}'. (Is the location name correct and has multiple equipment?)")

        # Example: Replace "ConstructAll Ltd." with an actual customer name from your data
        test_customer_name = "ConstructAll Ltd."
        print(f"\n3. Fetching Maintenance for Equipment operated by Customer: {test_customer_name} (Graph Query)")
        customer_maintenance = get_maintenance_for_customer_equipment_graph(db, customer_name_filter=test_customer_name, limit=5)
        if customer_maintenance is not None:
            print(json.dumps(customer_maintenance, indent=2))
        else:
            print(f"Failed to fetch maintenance for customer '{test_customer_name}'. (Is the customer name correct and do their equipment have maintenance jobs?)")
    else:
        print("\n--- db.py: Cannot run examples - Spanner database connection not established. ---")
        print("--- Please check GCP_PROJECT_ID, Spanner instance/database IDs, and permissions. ---")