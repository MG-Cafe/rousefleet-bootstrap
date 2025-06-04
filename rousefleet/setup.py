import os
import uuid
from datetime import datetime, timedelta, timezone
import time
import csv
from typing import Optional
from google.cloud import spanner
from google.api_core import exceptions
import random
INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID", "rousefleet-graph-instance")
DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID", "graphdb")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
EQUIPMENT_CSV_PATH = os.path.join(os.path.dirname(__file__), "fleet_equipment.csv")

database_client_object = None
try:
    if not PROJECT_ID:
        raise ValueError("CRITICAL: GOOGLE_CLOUD_PROJECT not set.")
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database_obj_from_spanner = instance.database(DATABASE_ID)
    print(f"Targeting Spanner: {instance.name}/databases/{database_obj_from_spanner.name}")
    if not database_obj_from_spanner.exists():
        print(f"Error: Database '{DATABASE_ID}' does not exist in instance '{INSTANCE_ID}'.")
        database_client_object = None
    else:
        print("Database connection successful.")
        database_client_object = database_obj_from_spanner
except Exception as e:
    print(f"Error initializing Spanner client: {e}")
    traceback.print_exc()
    database_client_object = None

def run_ddl_statements(db_instance, ddl_list, operation_description):
    if not db_instance:
        print(f"Skipping DDL ({operation_description}) - database connection not available.")
        return False
    print(f"\n--- Running DDL: {operation_description} ---")
    print("Statements:")
    for i, stmt in enumerate(ddl_list):
        print(f"  [{i+1}] {stmt.strip()}")
    try:
        operation = db_instance.update_ddl(ddl_list)
        print("Waiting for DDL operation to complete...")
        operation.result(360)
        print(f"DDL operation '{operation_description}' completed successfully.")
        return True
    except (exceptions.FailedPrecondition, exceptions.AlreadyExists) as e:
        print(f"Warning/Info during DDL '{operation_description}': {type(e).__name__} - {e}")
        print("Continuing script execution.")
        return True
    except Exception as e:
        print(f"ERROR during DDL '{operation_description}': {type(e).__name__} - {e}")
        traceback.print_exc()
        return False

def setup_fleet_schema_and_indexes(db_instance):
    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS ServiceLocation (location_id STRING(36) NOT NULL, name STRING(MAX), address STRING(MAX), city STRING(MAX), state_province STRING(MAX), postal_code STRING(MAX), country STRING(MAX), latitude FLOAT64, longitude FLOAT64, capacity INT64, create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true)) PRIMARY KEY (location_id)""",
        """CREATE TABLE IF NOT EXISTS Customer (customer_id STRING(36) NOT NULL, customer_name STRING(MAX), industry_type STRING(MAX), region STRING(MAX), create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true)) PRIMARY KEY (customer_id)""",
        """CREATE TABLE IF NOT EXISTS Equipment (equipment_id STRING(36) NOT NULL, serial_number STRING(MAX) NOT NULL, description STRING(MAX), list_price FLOAT64, meter_hours INT64, current_address STRING(MAX), current_city STRING(MAX), current_state_province STRING(MAX), current_postal_code STRING(MAX), current_country STRING(MAX), category STRING(MAX), subcategory STRING(MAX), make STRING(MAX), model STRING(MAX), model_year INT64, financing_eligible BOOL, warranty_eligible BOOL, photo_url STRING(MAX), video_url STRING(MAX), latitude FLOAT64, longitude FLOAT64, current_service_location_id STRING(36), current_customer_id STRING(36), create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true), CONSTRAINT FK_Equipment_ServiceLocation FOREIGN KEY (current_service_location_id) REFERENCES ServiceLocation (location_id), CONSTRAINT FK_Equipment_Customer FOREIGN KEY (current_customer_id) REFERENCES Customer (customer_id)) PRIMARY KEY (equipment_id)""",
        """CREATE TABLE IF NOT EXISTS MaintenanceJob (job_id STRING(36) NOT NULL, equipment_id STRING(36) NOT NULL, job_date TIMESTAMP, job_description STRING(MAX), cost FLOAT64, service_type STRING(MAX), create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true), CONSTRAINT FK_MaintenanceJob_Equipment FOREIGN KEY (equipment_id) REFERENCES Equipment (equipment_id)) PRIMARY KEY (job_id)""",
        """CREATE TABLE IF NOT EXISTS CustomerEquipmentAssignment (assignment_id STRING(36) NOT NULL, customer_id STRING(36) NOT NULL, equipment_id STRING(36) NOT NULL, assignment_start_date TIMESTAMP, assignment_end_date TIMESTAMP, assignment_type STRING(MAX), create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true), CONSTRAINT FK_Assignment_Customer FOREIGN KEY (customer_id) REFERENCES Customer (customer_id), CONSTRAINT FK_Assignment_Equipment FOREIGN KEY (equipment_id) REFERENCES Equipment (equipment_id)) PRIMARY KEY (assignment_id)""",
        "CREATE INDEX IF NOT EXISTS EquipmentBySerialNumber ON Equipment(serial_number)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCategoryMakeModel ON Equipment(category, make, model, model_year)",
        "CREATE INDEX IF NOT EXISTS EquipmentByLocation ON Equipment(current_city, current_state_province)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCurrentServiceLocation ON Equipment(current_service_location_id)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCurrentCustomer ON Equipment(current_customer_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS Equipment_serial_number_key ON Equipment(serial_number)",
        "CREATE INDEX IF NOT EXISTS MaintenanceJobByEquipment ON MaintenanceJob(equipment_id, job_date DESC)",
        "CREATE INDEX IF NOT EXISTS MaintenanceJobByDate ON MaintenanceJob(job_date DESC)",
        "CREATE INDEX IF NOT EXISTS CustomerByName ON Customer(customer_name)",
        "CREATE INDEX IF NOT EXISTS CustomerEquipmentAssignmentByCustomerEquipment ON CustomerEquipmentAssignment(customer_id, equipment_id)",
        "CREATE INDEX IF NOT EXISTS CustomerEquipmentAssignmentByEquipment ON CustomerEquipmentAssignment(equipment_id)",
    ]
    return run_ddl_statements(db_instance, ddl_statements, "Create FleetPro Base Tables and Indexes")

def setup_fleet_graph_definition(db_instance):
    ddl_statements = [
        """CREATE PROPERTY GRAPH IF NOT EXISTS FleetGraph NODE TABLES (Equipment KEY (equipment_id) LABEL EquipmentNode, ServiceLocation KEY (location_id) LABEL ServiceLocationNode, MaintenanceJob KEY (job_id) LABEL MaintenanceJobNode, Customer KEY (customer_id) LABEL CustomerNode) EDGE TABLES (MaintenanceJob AS PerformedOnEquipment SOURCE KEY (job_id) REFERENCES MaintenanceJob (equipment_id) DESTINATION KEY (equipment_id) REFERENCES Equipment (equipment_id), Equipment AS LocatedAtServiceDepot SOURCE KEY (equipment_id) REFERENCES Equipment (equipment_id) DESTINATION KEY (current_service_location_id) REFERENCES ServiceLocation (location_id), CustomerEquipmentAssignment AS OperatesEquipment SOURCE KEY (customer_id) REFERENCES Customer (customer_id) DESTINATION KEY (equipment_id) REFERENCES Equipment (equipment_id) PROPERTIES (assignment_type, assignment_start_date, assignment_end_date), CustomerEquipmentAssignment AS EquipmentOperatedBy SOURCE KEY (equipment_id) REFERENCES Equipment (equipment_id) DESTINATION KEY (customer_id) REFERENCES Customer (customer_id) PROPERTIES (assignment_type, assignment_start_date, assignment_end_date))"""
    ]
    return run_ddl_statements(db_instance, ddl_statements, "Create FleetPro Property Graph Definition")

CITY_COORDS = {
    "Toronto": (43.6532, -79.3832), "Boston": (42.3601, -71.0589),
    "Los Angeles": (34.0522, -118.2437), "Houston": (29.7604, -95.3698),
    "Calgary": (51.0447, -114.0719), "New York": (40.7128, -74.0060),
    "Chicago": (41.8781, -87.6298), "Dallas": (32.7767, -96.7970),
    "Seattle": (47.6062, -122.3321), "Miami": (25.7617, -80.1918)
}

def get_coords_for_city(city_name_param):
    base_lat, base_lon = CITY_COORDS.get(city_name_param, (37.0902, -95.7129)) # Default to US center
    return round(base_lat + random.uniform(-0.005, 0.005), 6), round(base_lon + random.uniform(-0.005, 0.005), 6)

def parse_bool_from_csv(value_str: str) -> Optional[bool]:
    if not value_str: return None
    return value_str.strip().upper() == 'TRUE'

def parse_float_from_csv(value_str: str) -> Optional[float]:
    if not value_str: return None
    try: return float(value_str)
    except ValueError: return None

def parse_int_from_csv(value_str: str) -> Optional[int]:
    if not value_str: return None
    try: return int(value_str)
    except ValueError: return None

def parse_datetime_from_csv(value_str: str) -> Optional[datetime]:
    if not value_str: return None
    try: 
        dt = datetime.fromisoformat(value_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError: return None

def deterministic_uuid(base_string: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{base_string}_{index}"))

def insert_fleet_data(db_instance):
    if not db_instance: print("Skipping data insertion - db connection unavailable."); return False
    print("\n--- Defining Fixed Data for FleetPro Relational Insertion ---")

    now = datetime.now(timezone.utc) # Used as a base for relative dates
    all_rows_to_insert = {}
    
    service_location_rows = []
    customer_rows = []
    equipment_rows_final = []
    maintenance_job_rows = []
    customer_equipment_assignment_rows = []

    service_location_map = {}
    customer_map = {}

    fixed_service_locations = [
        {"location_id": "SL_UUID_001", "name": "Toronto Central Depot", "address": "100 Industry Rd", "city": "Toronto", "state_province": "ON", "postal_code": "M5V 2T1", "country": "Canada", "capacity": 100},
        {"location_id": "SL_UUID_002", "name": "LAX Area Yard", "address": "200 Commerce Ave", "city": "Los Angeles", "state_province": "CA", "postal_code": "90045", "country": "USA", "capacity": 150},
        {"location_id": "SL_UUID_003", "name": "Houston South Terminal", "address": "300 Port Blvd", "city": "Houston", "state_province": "TX", "postal_code": "77002", "country": "USA", "capacity": 75},
        {"location_id": "SL_UUID_004", "name": "Calgary North Operations", "address": "400 Logistics Way", "city": "Calgary", "state_province": "AB", "postal_code": "T2P 0A1", "country": "Canada", "capacity": 90},
        {"location_id": "SL_UUID_005", "name": "Boston Metro Hub", "address": "500 Distribution St", "city": "Boston", "state_province": "MA", "postal_code": "02110", "country": "USA", "capacity": 60},
        {"location_id": "SL_UUID_006", "name": "NY Logistics Center", "address": "600 Transport Dr", "city": "New York", "state_province": "NY", "postal_code": "10001", "country": "USA", "capacity": 120},
    ]
    print(f"Preparing {len(fixed_service_locations)} service locations.")
    for loc_data in fixed_service_locations:
        service_location_map[loc_data["name"]] = loc_data["location_id"]
        lat, lon = get_coords_for_city(loc_data["city"]) # Keep slight randomness for map display variety if desired, or fix these too
        service_location_rows.append((
            loc_data["location_id"], loc_data["name"], loc_data["address"], loc_data["city"],
            loc_data["state_province"], loc_data["postal_code"], loc_data["country"],
            lat, lon, loc_data["capacity"], spanner.COMMIT_TIMESTAMP
        ))
    all_rows_to_insert["ServiceLocation"] = {"cols": ["location_id", "name", "address", "city", "state_province", "postal_code", "country", "latitude", "longitude", "capacity", "create_time"], "rows": service_location_rows}

    fixed_customers = [
        {"customer_id": "CUST_UUID_001", "name": "ConstructAll Ltd.", "industry": "Heavy Construction", "region": "North East"},
        {"customer_id": "CUST_UUID_002", "name": "RentWise Inc.", "industry": "Equipment Rental", "region": "West Coast"},
        {"customer_id": "CUST_UUID_003", "name": "AgriCorp Solutions", "industry": "Agriculture", "region": "Midwest"},
        {"customer_id": "CUST_UUID_004", "name": "InfraBuild Co.", "industry": "Infrastructure", "region": "South"},
        {"customer_id": "CUST_UUID_005", "name": "Precision Movers", "industry": "Logistics", "region": "Canada"},
        {"customer_id": "CUST_UUID_006", "name": "UrbanScape Developers", "industry": "Real Estate Development", "region": "East Coast"},
        {"customer_id": "CUST_UUID_007", "name": "TerraForm Earthworks", "industry": "Mining", "region": "West Canada"},
        {"customer_id": "CUST_UUID_008", "name": "HighRise Builders", "industry": "Commercial Construction", "region": "South West"},
        {"customer_id": "CUST_UUID_009", "name": "GreenField Landscaping", "industry": "Landscaping", "region": "Pacific North"},
        {"customer_id": "CUST_UUID_010", "name": "AllRoads Paving", "industry": "Road Construction", "region": "Central"},
    ]
    print(f"Preparing {len(fixed_customers)} customers.")
    for cust_data in fixed_customers:
        customer_map[cust_data["name"]] = cust_data["customer_id"]
        customer_rows.append((
            cust_data["customer_id"], cust_data["name"], cust_data["industry"],
            cust_data["region"], spanner.COMMIT_TIMESTAMP
        ))
    all_rows_to_insert["Customer"] = {"cols": ["customer_id", "customer_name", "industry_type", "region", "create_time"], "rows": customer_rows}
    
    equipment_from_csv = []
    try:
        with open(EQUIPMENT_CSV_PATH, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader: equipment_from_csv.append(row)
        print(f"Successfully loaded {len(equipment_from_csv)} equipment items from {EQUIPMENT_CSV_PATH}")
    except FileNotFoundError: print(f"ERROR: {EQUIPMENT_CSV_PATH} not found."); return False
    except Exception as e: print(f"ERROR reading {EQUIPMENT_CSV_PATH}: {e}"); traceback.print_exc(); return False

    if not equipment_from_csv: print("No equipment data from CSV."); return False

    for eq_csv_row in equipment_from_csv:
        eq_id = eq_csv_row.get("equipment_id")
        lat, lon = get_coords_for_city(eq_csv_row.get("city", ""))
        cust_id_from_csv = customer_map.get(eq_csv_row.get("assigned_customer_name"))
        loc_id_from_csv = service_location_map.get(eq_csv_row.get("assigned_service_location_name"))

        equipment_rows_final.append((
            eq_id, eq_csv_row.get("serial_number"), eq_csv_row.get("description"),
            parse_float_from_csv(eq_csv_row.get("list_price")), parse_int_from_csv(eq_csv_row.get("meter_hours")),
            eq_csv_row.get("current_address"), eq_csv_row.get("current_city"), eq_csv_row.get("current_state_province"),
            eq_csv_row.get("current_postal_code"), eq_csv_row.get("current_country"),
            eq_csv_row.get("category"), eq_csv_row.get("subcategory"), eq_csv_row.get("make"), eq_csv_row.get("model"),
            parse_int_from_csv(eq_csv_row.get("model_year")),
            parse_bool_from_csv(eq_csv_row.get("financing_eligible", "FALSE")),
            parse_bool_from_csv(eq_csv_row.get("warranty_eligible", "FALSE")),
            eq_csv_row.get("photo_url"), eq_csv_row.get("video_url"),
            lat, lon, loc_id_from_csv, cust_id_from_csv, spanner.COMMIT_TIMESTAMP
        ))
    all_rows_to_insert["Equipment"] = {"cols": ["equipment_id", "serial_number", "description", "list_price", "meter_hours", "current_address", "current_city", "current_state_province", "current_postal_code", "current_country", "category", "subcategory", "make", "model", "model_year", "financing_eligible", "warranty_eligible", "photo_url", "video_url", "latitude", "longitude", "current_service_location_id", "current_customer_id", "create_time"], "rows": equipment_rows_final}

    fixed_job_details = [
        {"desc_idx": 0, "cost": 150.75, "type_idx": 0, "days_offset": 220}, {"desc_idx": 1, "cost": 85.00, "type_idx": 5, "days_offset": 80},
        {"desc_idx": 2, "cost": 250.00, "type_idx": 2, "days_offset": 180}, {"desc_idx": 3, "cost": 320.50, "type_idx": 1, "days_offset": 40},
        {"desc_idx": 4, "cost": 120.00, "type_idx": 6, "days_offset": 280}, {"desc_idx": 0, "cost": 450.00, "type_idx": 0, "days_offset": 110},
    ]
    service_types = ["Scheduled Maintenance", "Repair - Engine", "Inspection - Safety", "Repair - Hydraulics", "Tire Replacement", "Oil Change", "Filter Replacement"]
    job_descriptions = ["Performed service as per guidelines.", "Replaced faulty starter.", "Annual safety inspection passed.", "Fixed hydraulic leak.", "Replaced two front tires.", "Completed oil change.", "Replaced air and fuel filters."]
    
    job_uuid_counter = 1
    for i, eq_row_tuple in enumerate(equipment_rows_final):
        eq_id_for_job = eq_row_tuple[0] 
        sn_for_job = eq_row_tuple[1]
        for j in range(2): # Create 2 fixed jobs per equipment
            job_detail_template = fixed_job_details[(i*2 + j) % len(fixed_job_details)]
            job_id = deterministic_uuid("MJ_UUID", job_uuid_counter)
            job_uuid_counter +=1
            job_date_dt = now - timedelta(days=job_detail_template["days_offset"], hours=i, minutes=j*10)
            desc = job_descriptions[job_detail_template["desc_idx"] % len(job_descriptions)] + f" Unit SN: {sn_for_job}"
            stype = service_types[job_detail_template["type_idx"] % len(service_types)]
            maintenance_job_rows.append((
                job_id, eq_id_for_job, job_date_dt, desc, job_detail_template["cost"], stype, spanner.COMMIT_TIMESTAMP
            ))
    all_rows_to_insert["MaintenanceJob"] = {"cols": ["job_id", "equipment_id", "job_date", "job_description", "cost", "service_type", "create_time"], "rows": maintenance_job_rows}
    print(f"Prepared {len(maintenance_job_rows)} fixed maintenance jobs.")

    assignment_types = ["Owned", "Leased", "Rented - Long Term", "Rented - Short Term"]
    assign_uuid_counter = 1
    for i, eq_row_tuple in enumerate(equipment_rows_final):
        eq_id_for_assign = eq_row_tuple[0]
        cust_id_for_assign = eq_row_tuple[22] # current_customer_id is the 23rd element (index 22)
        if cust_id_for_assign:
            assignment_id = deterministic_uuid("ASSIGN_UUID", assign_uuid_counter)
            assign_uuid_counter += 1
            start_date_dt = now - timedelta(days=365 + i*10) # Deterministic start date
            assign_type = assignment_types[i % len(assignment_types)]
            end_date_dt = None
            if "Rented - Short Term" in assign_type: end_date_dt = start_date_dt + timedelta(days=60 + i*5)
            elif "Leased" in assign_type or "Rented - Long Term" in assign_type : end_date_dt = start_date_dt + timedelta(days=365 + i*15)
            customer_equipment_assignment_rows.append((
                assignment_id, cust_id_for_assign, eq_id_for_assign,
                start_date_dt, end_date_dt, assign_type, spanner.COMMIT_TIMESTAMP
            ))
    all_rows_to_insert["CustomerEquipmentAssignment"] = {"cols": ["assignment_id", "customer_id", "equipment_id", "assignment_start_date", "assignment_end_date", "assignment_type", "create_time"], "rows": customer_equipment_assignment_rows}
    print(f"Prepared {len(customer_equipment_assignment_rows)} fixed customer equipment assignments.")

    print("\n--- Inserting All Fixed Data into FleetPro Relational Tables ---")
    table_insert_order = ["ServiceLocation", "Customer", "Equipment", "MaintenanceJob", "CustomerEquipmentAssignment"]
    try:
        with db_instance.batch() as batch:
            for table_name in table_insert_order:
                if table_name in all_rows_to_insert:
                    table_data = all_rows_to_insert[table_name]
                    if table_data["rows"]:
                        print(f"Inserting {len(table_data['rows'])} rows into {table_name}...")
                        batch.insert(table=table_name, columns=table_data["cols"], values=table_data["rows"])
        print("Data insertion transaction committed successfully.")
        for table_name in table_insert_order:
             if table_name in all_rows_to_insert and all_rows_to_insert[table_name]["rows"]:
                print(f"  -> Inserted {len(all_rows_to_insert[table_name]['rows'])} rows into {table_name}.")
        return True
    except Exception as e:
        print(f"ERROR during batch data insertion: {type(e).__name__} - {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting Spanner FleetPro Schema Setup Script (CSV for Equipment, Fixed for Others)...")
    start_time = time.time()
    if not PROJECT_ID: print("\nCRITICAL ERROR: GOOGLE_CLOUD_PROJECT environment variable not set. Aborting."); exit(1)
    if not database_client_object: print("\nCritical Error: Spanner database connection not established. Aborting."); exit(1)
    if not setup_fleet_schema_and_indexes(database_client_object): print("\nAborting: errors during schema/index creation."); exit(1)
    if not setup_fleet_graph_definition(database_client_object): print("\nAborting: errors during graph definition creation."); exit(1)
    if not insert_fleet_data(database_client_object): print("\nScript finished with errors during data insertion."); exit(1)
    end_time = time.time()
    print("\n-----------------------------------------")
    print("Rouse FleetPro Spanner Setup Script finished successfully!")
    print(f"Database '{DATABASE_ID}' on instance '{INSTANCE_ID}' set up with schema, graph, and data.")
    print(f"Total time: {end_time - start_time:.2f} seconds")
    print("-----------------------------------------")
