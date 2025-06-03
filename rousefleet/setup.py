import os
import uuid
from datetime import datetime, timedelta, timezone
# from dateutil import parser as dateutil_parser # Not used in this script
import time
import random

from google.cloud import spanner
from google.api_core import exceptions

# --- Configuration ---
INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID", "rousefleet-graph-instance")
DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID", "graphdb")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")


# --- Spanner Client Initialization ---
try:
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)
    print(f"Targeting Spanner: {instance.name}/databases/{database.name}")
    if not database.exists():
        print(f"Error: Database '{DATABASE_ID}' does not exist in instance '{INSTANCE_ID}'.")
        print("Please create the database first or ensure the instance and database IDs are correct.")
        database = None
    else:
        print("Database connection successful.")
except exceptions.NotFound:
    print(f"Error: Spanner instance '{INSTANCE_ID}' not found or missing permissions for project '{PROJECT_ID}'.")
    spanner_client = None; instance = None; database = None
except Exception as e:
    print(f"Error initializing Spanner client: {e}")
    spanner_client = None; instance = None; database = None

def run_ddl_statements(db_instance, ddl_list, operation_description):
    """Helper function to run DDL statements and handle potential errors."""
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
        operation.result(360) # Wait up to 6 minutes
        print(f"DDL operation '{operation_description}' completed successfully.")
        return True
    except (exceptions.FailedPrecondition, exceptions.AlreadyExists) as e:
        print(f"Warning/Info during DDL '{operation_description}': {type(e).__name__} - {e}")
        print("Continuing script execution (schema object might already exist or precondition failed).")
        return True
    except exceptions.InvalidArgument as e:
        print(f"ERROR during DDL '{operation_description}': {type(e).__name__} - {e}")
        print(">>> This indicates a DDL syntax error. The schema was NOT created/updated correctly. Stopping script. <<<")
        return False
    except exceptions.DeadlineExceeded:
        print(f"ERROR during DDL '{operation_description}': DeadlineExceeded - Operation took too long.")
        return False
    except Exception as e:
        print(f"ERROR during DDL '{operation_description}': {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        print("Stopping script due to unexpected DDL error.")
        return False

def setup_fleet_schema_and_indexes(db_instance):
    """Creates the base relational tables and associated indexes for the FleetPro demo."""
    ddl_statements = [
        # --- 1. Base Tables for FleetPro ---
        """
        CREATE TABLE IF NOT EXISTS ServiceLocation (
            location_id STRING(36) NOT NULL,
            name STRING(MAX),
            address STRING(MAX),
            city STRING(MAX),
            state_province STRING(MAX),
            postal_code STRING(MAX),
            country STRING(MAX),
            latitude FLOAT64,
            longitude FLOAT64,
            capacity INT64,
            create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true)
        ) PRIMARY KEY (location_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS Customer (
            customer_id STRING(36) NOT NULL,
            customer_name STRING(MAX),
            industry_type STRING(MAX),
            region STRING(MAX),
            create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true)
        ) PRIMARY KEY (customer_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS Equipment (
            equipment_id STRING(36) NOT NULL,
            serial_number STRING(MAX) NOT NULL,
            description STRING(MAX),
            list_price FLOAT64,
            meter_hours INT64,
            current_address STRING(MAX),
            current_city STRING(MAX),
            current_state_province STRING(MAX),
            current_postal_code STRING(MAX),
            current_country STRING(MAX),
            category STRING(MAX),
            subcategory STRING(MAX),
            make STRING(MAX),
            model STRING(MAX),
            model_year INT64,
            financing_eligible BOOL,
            warranty_eligible BOOL,
            photo_url STRING(MAX),
            video_url STRING(MAX),
            latitude FLOAT64,
            longitude FLOAT64,
            current_service_location_id STRING(36), -- FK to ServiceLocation
            current_customer_id STRING(36),         -- FK to Customer
            create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true),
            CONSTRAINT FK_Equipment_ServiceLocation FOREIGN KEY (current_service_location_id) REFERENCES ServiceLocation (location_id),
            CONSTRAINT FK_Equipment_Customer FOREIGN KEY (current_customer_id) REFERENCES Customer (customer_id)
        ) PRIMARY KEY (equipment_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS MaintenanceJob (
            job_id STRING(36) NOT NULL,
            equipment_id STRING(36) NOT NULL, -- FK to Equipment
            job_date TIMESTAMP,
            job_description STRING(MAX),
            cost FLOAT64,
            service_type STRING(MAX), -- e.g., "Scheduled", "Repair", "Inspection"
            create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true),
            CONSTRAINT FK_MaintenanceJob_Equipment FOREIGN KEY (equipment_id) REFERENCES Equipment (equipment_id)
        ) PRIMARY KEY (job_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS CustomerEquipmentAssignment (
            assignment_id STRING(36) NOT NULL,
            customer_id STRING(36) NOT NULL, -- FK to Customer
            equipment_id STRING(36) NOT NULL, -- FK to Equipment
            assignment_start_date TIMESTAMP,
            assignment_end_date TIMESTAMP,
            assignment_type STRING(MAX), -- e.g., "Owned", "Leased", "Rented"
            create_time TIMESTAMP NOT NULL OPTIONS(allow_commit_timestamp=true),
            CONSTRAINT FK_Assignment_Customer FOREIGN KEY (customer_id) REFERENCES Customer (customer_id),
            CONSTRAINT FK_Assignment_Equipment FOREIGN KEY (equipment_id) REFERENCES Equipment (equipment_id)
        ) PRIMARY KEY (assignment_id)
        """,

        # --- 2. Indexes ---
        "CREATE INDEX IF NOT EXISTS EquipmentBySerialNumber ON Equipment(serial_number)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCategoryMakeModel ON Equipment(category, make, model, model_year)",
        "CREATE INDEX IF NOT EXISTS EquipmentByLocation ON Equipment(current_city, current_state_province)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCurrentServiceLocation ON Equipment(current_service_location_id)",
        "CREATE INDEX IF NOT EXISTS EquipmentByCurrentCustomer ON Equipment(current_customer_id)",
        "CREATE INDEX IF NOT EXISTS MaintenanceJobByEquipment ON MaintenanceJob(equipment_id, job_date DESC)",
        "CREATE INDEX IF NOT EXISTS MaintenanceJobByDate ON MaintenanceJob(job_date DESC)",
        "CREATE INDEX IF NOT EXISTS CustomerByName ON Customer(customer_name)",
        "CREATE INDEX IF NOT EXISTS CustomerEquipmentAssignmentByCustomerEquipment ON CustomerEquipmentAssignment(customer_id, equipment_id)",
        "CREATE INDEX IF NOT EXISTS CustomerEquipmentAssignmentByEquipment ON CustomerEquipmentAssignment(equipment_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS Equipment_serial_number_key ON Equipment(serial_number)",
    ]
    return run_ddl_statements(db_instance, ddl_statements, "Create FleetPro Base Tables and Indexes")

def setup_fleet_graph_definition(db_instance):
    """Creates the Property Graph definition for the FleetPro demo."""
    ddl_statements = [
        """
        CREATE PROPERTY GRAPH IF NOT EXISTS FleetGraph
          NODE TABLES (
            Equipment KEY (equipment_id) LABEL EquipmentNode,
            ServiceLocation KEY (location_id) LABEL ServiceLocationNode,
            MaintenanceJob KEY (job_id) LABEL MaintenanceJobNode,
            Customer KEY (customer_id) LABEL CustomerNode
          )
          EDGE TABLES (
            MaintenanceJob AS PerformedOnEquipment
              SOURCE KEY (job_id) REFERENCES MaintenanceJob (job_id)
              DESTINATION KEY (equipment_id) REFERENCES Equipment (equipment_id),

            Equipment AS LocatedAtServiceDepot
              SOURCE KEY (equipment_id) REFERENCES Equipment (equipment_id)
              DESTINATION KEY (current_service_location_id) REFERENCES ServiceLocation (location_id),

            CustomerEquipmentAssignment AS OperatesEquipment
              SOURCE KEY (customer_id) REFERENCES Customer (customer_id)
              DESTINATION KEY (equipment_id) REFERENCES Equipment (equipment_id)
              PROPERTIES (assignment_type, assignment_start_date, assignment_end_date),

            CustomerEquipmentAssignment AS EquipmentOperatedBy
              SOURCE KEY (equipment_id) REFERENCES Equipment (equipment_id)
              DESTINATION KEY (customer_id) REFERENCES Customer (customer_id)
              PROPERTIES (assignment_type, assignment_start_date, assignment_end_date)
          )
        """
    ]
    return run_ddl_statements(db_instance, ddl_statements, "Create FleetPro Property Graph Definition")

def generate_uuid(): return str(uuid.uuid4())

CITY_COORDS = {
    "Toronto": (43.6532, -79.3832), "Boston": (42.3601, -71.0589),
    "Los Angeles": (34.0522, -118.2437), "Houston": (29.7604, -95.3698),
    "Calgary": (51.0447, -114.0719), "New York": (40.7128, -74.0060),
    "Chicago": (41.8781, -87.6298), "Dallas": (32.7767, -96.7970),
    "Seattle": (47.6062, -122.3321), "Miami": (25.7617, -80.1918)
}

def get_coords_for_city(city_name):
    base_lat, base_lon = CITY_COORDS.get(city_name, (0.0, 0.0)) # Default if city not found
    # Add slight random variation to make coordinates unique if multiple items are in the same city center
    return round(base_lat + random.uniform(-0.005, 0.005), 6), round(base_lon + random.uniform(-0.005, 0.005), 6)


def insert_fleet_data(db_instance):
    if not db_instance: print("Skipping data insertion - db connection unavailable."); return False
    print("\n--- Defining Curated Data for FleetPro Relational Insertion ---")

    now = datetime.now(timezone.utc)
    service_location_rows, customer_rows, equipment_rows_final = [], [], []
    maintenance_job_rows, customer_equipment_assignment_rows = [], []
    service_location_map, customer_map, equipment_map = {}, {}, {} # equipment_map maps placeholder to real ID

    service_location_data = [
        {"name": "Toronto Central Depot", "city": "Toronto", "state_province": "ON", "country": "Canada", "capacity": 100},
        {"name": "LAX Area Yard", "city": "Los Angeles", "state_province": "CA", "country": "USA", "capacity": 150},
        {"name": "Houston South Terminal", "city": "Houston", "state_province": "TX", "country": "USA", "capacity": 75},
        {"name": "Calgary North Operations", "city": "Calgary", "state_province": "AB", "country": "Canada", "capacity": 90},
        {"name": "Boston Metro Hub", "city": "Boston", "state_province": "MA", "country": "USA", "capacity": 60},
        {"name": "NY Logistics Center", "city": "New York", "state_province": "NY", "country": "USA", "capacity": 120},
    ]
    print(f"Preparing {len(service_location_data)} service locations.")
    for loc_data in service_location_data:
        loc_id = generate_uuid()
        service_location_map[loc_data["name"]] = loc_id
        lat, lon = get_coords_for_city(loc_data["city"])
        service_location_rows.append({
            "location_id": loc_id, "name": loc_data["name"],
            "address": f"{random.randint(100,9999)} Industrial Way", "city": loc_data["city"],
            "state_province": loc_data["state_province"], "postal_code": f"{random.randint(10000,99999)}",
            "country": loc_data["country"], "latitude": lat, "longitude": lon,
            "capacity": loc_data["capacity"], "create_time": spanner.COMMIT_TIMESTAMP
        })

    customer_data = [
        {"name": "ConstructAll Ltd.", "industry": "Heavy Construction", "region": "North East"},
        {"name": "RentWise Inc.", "industry": "Equipment Rental", "region": "West Coast"},
        {"name": "AgriCorp Solutions", "industry": "Agriculture", "region": "Midwest"},
        {"name": "InfraBuild Co.", "industry": "Infrastructure", "region": "South"},
        {"name": "Precision Movers", "industry": "Logistics", "region": "Canada"},
        {"name": "UrbanScape Developers", "industry": "Real Estate Development", "region": "East Coast"},
        {"name": "TerraForm Earthworks", "industry": "Mining", "region": "West Canada"},
        {"name": "HighRise Builders", "industry": "Commercial Construction", "region": "South West"},
        {"name": "GreenField Landscaping", "industry": "Landscaping", "region": "Pacific North"},
        {"name": "AllRoads Paving", "industry": "Road Construction", "region": "Central"},
    ]
    print(f"Preparing {len(customer_data)} customers.")
    for cust_data in customer_data:
        cust_id = generate_uuid()
        customer_map[cust_data["name"]] = cust_id
        customer_rows.append({
            "customer_id": cust_id, "customer_name": cust_data["name"],
            "industry_type": cust_data["industry"], "region": cust_data["region"],
            "create_time": spanner.COMMIT_TIMESTAMP
        })

    # --- UPDATED equipment_base_data with local static image paths ---
    equipment_base_data = [
        {"equipment_id_placeholder": "EQ001", "serial_number": "SNRW3GEN001", "description": "19ft Electric Scissor Lift", "list_price": 18000.00, "meter_hours": 150, "address": "123 Main St", "city": "Toronto", "state_province": "ON", "postal_code": "M5V 2N1", "country": "Canada", "category": "Aerial Lifts", "subcategory": "Scissor Lifts", "make": "Genie", "model": "GS-1930", "model_year": 2022, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNRW3GEN001.jpg", "video_url": "/static/videos/SNRW3GEN001.mp4"},
        {"equipment_id_placeholder": "EQ002", "serial_number": "SNJDEXC002", "description": "Compact Excavator with Cab", "list_price": 75000.00, "meter_hours": 1250, "address": "456 Oak Ave", "city": "Los Angeles", "state_province": "CA", "postal_code": "90001", "country": "USA", "category": "Earthmoving", "subcategory": "Excavators", "make": "John Deere", "model": "35G", "model_year": 2020, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNJDEXC002.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ003", "serial_number": "SNCATSKD003", "description": "Skid Steer Loader", "list_price": 55000.00, "meter_hours": 800, "address": "789 Pine Rd", "city": "Houston", "state_province": "TX", "postal_code": "77002", "country": "USA", "category": "Earthmoving", "subcategory": "Skid Steer Loaders", "make": "Caterpillar", "model": "272D3", "model_year": 2021, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNCATSKD003.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ004", "serial_number": "SNJLGBL004", "description": "Articulating Boom Lift 45ft", "list_price": 92000.00, "meter_hours": 600, "address": "101 Maple Dr", "city": "Calgary", "state_province": "AB", "postal_code": "T2P 2V7", "country": "Canada", "category": "Aerial Lifts", "subcategory": "Articulating Boom Lifts", "make": "JLG", "model": "450AJ", "model_year": 2022, "financing_eligible": False, "warranty_eligible": True, "photo_url": "/static/images/SNJLGBL004.jpg", "video_url": "/static/videos/SNJLGBL004.mp4"},
        {"equipment_id_placeholder": "EQ005", "serial_number": "SNVOLVOEX005", "description": "Large Crawler Excavator", "list_price": 280000.00, "meter_hours": 3500, "address": "234 Birch Ln", "city": "Toronto", "state_province": "ON", "postal_code": "M4B 1B4", "country": "Canada", "category": "Earthmoving", "subcategory": "Excavators", "make": "Volvo", "model": "EC380EL", "model_year": 2019, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNVOLVOEX005.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ006", "serial_number": "SNBCSKID006", "description": "Compact Track Loader", "list_price": 68000.00, "meter_hours": 450, "address": "567 Cedar St", "city": "Boston", "state_province": "MA", "postal_code": "02101", "country": "USA", "category": "Earthmoving", "subcategory": "Skid Steer Loaders", "make": "Bobcat", "model": "T66", "model_year": 2023, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNBCSKID006.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ007", "serial_number": "SNKOMEXC007", "description": "Mid-Size Excavator", "list_price": 180000.00, "meter_hours": 2100, "address": "890 Willow Ave", "city": "Los Angeles", "state_province": "CA", "postal_code": "90013", "country": "USA", "category": "Earthmoving", "subcategory": "Excavators", "make": "Komatsu", "model": "PC210LC-11", "model_year": 2020, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNKOMEXC007.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ008", "serial_number": "SNGENIEABL008", "description": "60ft Telescopic Boom Lift", "list_price": 115000.00, "meter_hours": 980, "address": "111 Aspen Rd", "city": "Houston", "state_province": "TX", "postal_code": "77008", "country": "USA", "category": "Aerial Lifts", "subcategory": "Telescopic Boom Lifts", "make": "Genie", "model": "S-60 XC", "model_year": 2021, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNGENIEABL008.jpg", "video_url": "/static/videos/SNGENIEABL008.mp4"},
        {"equipment_id_placeholder": "EQ009", "serial_number": "SNCASEBL009", "description": "Compact Backhoe Loader", "list_price": 88000.00, "meter_hours": 1500, "address": "222 Spruce Dr", "city": "Calgary", "state_province": "AB", "postal_code": "T2P 2V8", "country": "Canada", "category": "Earthmoving", "subcategory": "Backhoe Loaders", "make": "Case", "model": "580SN", "model_year": 2019, "financing_eligible": False, "warranty_eligible": False, "photo_url": "/static/images/SNCASEBL009.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ010", "serial_number": "SNKUBOTAUTV010", "description": "Utility Vehicle 4-Seater", "list_price": 22000.00, "meter_hours": 300, "address": "333 Redwood Cr", "city": "Toronto", "state_province": "ON", "postal_code": "M5R 1A1", "country": "Canada", "category": "Utility Vehicles", "subcategory": "UTVs", "make": "Kubota", "model": "RTV-XG850 Sidekick", "model_year": 2023, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNKUBOTAUTV010.jpg", "video_url": "/static/videos/SNKUBOTAUTV010.mp4"},
        {"equipment_id_placeholder": "EQ011", "serial_number": "SNDEEREAG011", "description": "Row Crop Tractor", "list_price": 150000.00, "meter_hours": 2200, "address": "Farm Rd 1", "city": "Dallas", "state_province": "TX", "postal_code": "75201", "country": "USA", "category": "Agricultural Equipment", "subcategory": "Tractors", "make": "John Deere", "model": "6155R", "model_year": 2020, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNDEEREAG011.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ012", "serial_number": "SNSKYJACKSL012", "description": "32ft Electric Scissor Lift", "list_price": 25000.00, "meter_hours": 450, "address": "Warehouse Ave 7", "city": "Chicago", "state_province": "IL", "postal_code": "60607", "country": "USA", "category": "Aerial Lifts", "subcategory": "Scissor Lifts", "make": "Skyjack", "model": "SJIII 3219", "model_year": 2022, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNSKYJACKSL012.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ013", "serial_number": "SNCATDOZER013", "description": "Medium Bulldozer", "list_price": 320000.00, "meter_hours": 4100, "address": "Quarry Site A", "city": "Seattle", "state_province": "WA", "postal_code": "98101", "country": "USA", "category": "Earthmoving", "subcategory": "Dozers", "make": "Caterpillar", "model": "D6T", "model_year": 2018, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNCATDOZER013.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ014", "serial_number": "SNJLGTELE014", "description": "Telehandler 10k lbs", "list_price": 110000.00, "meter_hours": 1800, "address": "Construction Yard 3", "city": "Miami", "state_province": "FL", "postal_code": "33101", "country": "USA", "category": "Material Handling", "subcategory": "Telehandlers", "make": "JLG", "model": "1055", "model_year": 2019, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNJLGTELE014.jpg", "video_url": "/static/videos/SNJLGTELE014.mp4"},
        {"equipment_id_placeholder": "EQ015", "serial_number": "SNVOLVOWHL015", "description": "Wheel Loader Medium", "list_price": 210000.00, "meter_hours": 3300, "address": "Port Authority Dock 5", "city": "New York", "state_province": "NY", "postal_code": "10004", "country": "USA", "category": "Earthmoving", "subcategory": "Wheel Loaders", "make": "Volvo", "model": "L120H", "model_year": 2020, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNVOLVOWHL015.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ016", "serial_number": "SNBCMINIEX016", "description": "Mini Excavator", "list_price": 45000.00, "meter_hours": 750, "address": "Residential Project Alpha", "city": "Toronto", "state_province": "ON", "postal_code": "M6K 1X9", "country": "Canada", "category": "Earthmoving", "subcategory": "Mini Excavators", "make": "Bobcat", "model": "E35", "model_year": 2022, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNBCMINIEX016.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ017", "serial_number": "SNGENIETL017", "description": "Trailer Mounted Boom Lift", "list_price": 65000.00, "meter_hours": 550, "address": "Rental Yard South", "city": "Los Angeles", "state_province": "CA", "postal_code": "90210", "country": "USA", "category": "Aerial Lifts", "subcategory": "Trailer Mounted Boom Lifts", "make": "Genie", "model": "TZ-50", "model_year": 2021, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNGENIETL017.jpg", "video_url": "/static/videos/SNGENIETL017.mp4"},
        {"equipment_id_placeholder": "EQ018", "serial_number": "SNMANITOUFORK018", "description": "Rough Terrain Forklift", "list_price": 78000.00, "meter_hours": 1200, "address": "Lumber Mill Site", "city": "Seattle", "state_province": "WA", "postal_code": "98104", "country": "USA", "category": "Material Handling", "subcategory": "Forklifts", "make": "Manitou", "model": "M50-4", "model_year": 2019, "financing_eligible": True, "warranty_eligible": False, "photo_url": "/static/images/SNMANITOUFORK018.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ019", "serial_number": "SNCASECOMP019", "description": "Soil Compactor", "list_price": 130000.00, "meter_hours": 2800, "address": "Highway Project 101", "city": "Houston", "state_province": "TX", "postal_code": "77042", "country": "USA", "category": "Compaction", "subcategory": "Soil Compactors", "make": "Case", "model": "SV216D", "model_year": 2020, "financing_eligible": False, "warranty_eligible": False, "photo_url": "/static/images/SNCASECOMP019.jpg", "video_url": ""},
        {"equipment_id_placeholder": "EQ020", "serial_number": "SNKUBOTATRAC020", "description": "Compact Tractor with Loader", "list_price": 35000.00, "meter_hours": 600, "address": "Small Farm Holdings", "city": "Calgary", "state_province": "AB", "postal_code": "T3A 0A1", "country": "Canada", "category": "Agricultural Equipment", "subcategory": "Compact Tractors", "make": "Kubota", "model": "LX2610HSD", "model_year": 2022, "financing_eligible": True, "warranty_eligible": True, "photo_url": "/static/images/SNKUBOTATRAC020.jpg", "video_url": "/static/videos/SNKUBOTATRAC020.mp4"},
    ]
    # --- End of UPDATED equipment_base_data ---

    print(f"Preparing {len(equipment_base_data)} equipment items.")
    for eq_data in equipment_base_data:
        eq_id = generate_uuid()
        equipment_map[eq_data["equipment_id_placeholder"]] = eq_id
        lat, lon = get_coords_for_city(eq_data["city"])
        # Assign a random service location and customer for initial data
        assigned_location_name = random.choice(list(service_location_map.keys())) if service_location_map else None
        assigned_customer_name = random.choice(list(customer_map.keys())) if customer_map else None
        equipment_rows_final.append({
            "equipment_id": eq_id,
            "serial_number": eq_data["serial_number"],
            "description": eq_data["description"],
            "list_price": eq_data.get("list_price"),
            "meter_hours": eq_data.get("meter_hours"),
            "current_address": eq_data["address"],
            "current_city": eq_data["city"],
            "current_state_province": eq_data["state_province"],
            "current_postal_code": eq_data["postal_code"],
            "current_country": eq_data["country"],
            "category": eq_data["category"],
            "subcategory": eq_data["subcategory"],
            "make": eq_data["make"],
            "model": eq_data["model"],
            "model_year": eq_data.get("model_year"),
            "financing_eligible": eq_data.get("financing_eligible"),
            "warranty_eligible": eq_data.get("warranty_eligible"),
            "photo_url": eq_data.get("photo_url"), # This will now use the updated paths
            "video_url": eq_data.get("video_url"), # Kept example video URLs, update if you have local videos
            "latitude": lat, "longitude": lon,
            "current_service_location_id": service_location_map.get(assigned_location_name),
            "current_customer_id": customer_map.get(assigned_customer_name),
            "create_time": spanner.COMMIT_TIMESTAMP
        })

    service_types = ["Scheduled Maintenance", "Repair - Engine", "Inspection - Safety", "Repair - Hydraulics", "Tire Replacement", "Oil Change", "Filter Replacement"]
    job_descriptions = [
        "Performed 500-hour service as per manufacturer guidelines. All checks passed.",
        "Replaced faulty starter motor and tested ignition system.",
        "Annual safety and compliance inspection. All systems nominal.",
        "Fixed hydraulic leak on main boom cylinder. Replaced seals.",
        "Replaced two front tires due to excessive wear. Alignment checked.",
        "Completed standard oil and fluids change.",
        "Replaced air and fuel filters."
    ]
    print(f"Preparing maintenance jobs for {len(equipment_rows_final)} equipment items.")
    for eq_row in equipment_rows_final:
        num_jobs = random.randint(1, 4) # Increased max jobs for more data
        for _ in range(num_jobs):
            job_id = generate_uuid()
            # Ensure job_date is a datetime object, aware of timezone
            job_date_dt = now - timedelta(days=random.randint(1, 730), hours=random.randint(0,23), minutes=random.randint(0,59))
            maintenance_job_rows.append({
                "job_id": job_id,
                "equipment_id": eq_row["equipment_id"],
                "job_date": job_date_dt, # Pass datetime object directly
                "job_description": random.choice(job_descriptions) + f" Unit SN: {eq_row['serial_number']}",
                "cost": round(random.uniform(50.0, 3500.0), 2),
                "service_type": random.choice(service_types),
                "create_time": spanner.COMMIT_TIMESTAMP
            })
    print(f"Prepared {len(maintenance_job_rows)} maintenance job rows.")

    assignment_types = ["Owned", "Leased", "Rented - Long Term", "Rented - Short Term", "Internal Project"]
    print(f"Preparing customer equipment assignments.")
    for eq_row in equipment_rows_final:
        # Assign to the initially selected customer for simplicity in this dataset
        if eq_row["current_customer_id"]:
            assignment_id = generate_uuid()
            # Ensure assignment_start_date is a datetime object, aware of timezone
            start_date_dt = now - timedelta(days=random.randint(30, 1095)) # Assigned in the last 3 years
            assignment_type_choice = random.choice(assignment_types)
            
            end_date_dt = None # Initialize as None
            if "Rented - Short Term" in assignment_type_choice:
                 end_date_dt = start_date_dt + timedelta(days=random.randint(7, 90))
            elif "Leased" in assignment_type_choice or "Rented - Long Term" in assignment_type_choice :
                 end_date_dt = start_date_dt + timedelta(days=random.randint(365, 1095))
            # 'Owned' or 'Internal Project' might not have an end date or a very far future one.

            customer_equipment_assignment_rows.append({
                "assignment_id": assignment_id,
                "customer_id": eq_row["current_customer_id"],
                "equipment_id": eq_row["equipment_id"],
                "assignment_start_date": start_date_dt, # Pass datetime object
                "assignment_end_date": end_date_dt,     # Pass datetime object or None
                "assignment_type": assignment_type_choice,
                "create_time": spanner.COMMIT_TIMESTAMP
            })
    print(f"Prepared {len(customer_equipment_assignment_rows)} customer equipment assignment rows.")

    print("\n--- Inserting Data into FleetPro Relational Tables ---")
    inserted_counts = {}
    def insert_data_txn(transaction):
        total_rows_attempted = 0
        # Define structure: Table Name -> (Columns List, Rows Data List of Dicts)
        table_map = {
            "ServiceLocation": (list(service_location_rows[0].keys()) if service_location_rows else [], service_location_rows),
            "Customer": (list(customer_rows[0].keys()) if customer_rows else [], customer_rows),
            "Equipment": (list(equipment_rows_final[0].keys()) if equipment_rows_final else [], equipment_rows_final),
            "MaintenanceJob": (list(maintenance_job_rows[0].keys()) if maintenance_job_rows else [], maintenance_job_rows),
            "CustomerEquipmentAssignment": (list(customer_equipment_assignment_rows[0].keys()) if customer_equipment_assignment_rows else [], customer_equipment_assignment_rows),
        }

        for table_name, (cols, rows_dict_list) in table_map.items():
            if rows_dict_list and cols:
                # print(f"Preparing to insert {len(rows_dict_list)} rows into {table_name}...")
                values_list = []
                for row_dict in rows_dict_list:
                    try:
                        # Ensure values are in the correct order as per 'cols'
                        # Datetime objects should be passed directly for TIMESTAMP columns
                        # Spanner.COMMIT_TIMESTAMP is also handled directly.
                        current_values = []
                        for col_name in cols:
                            current_values.append(row_dict.get(col_name))
                        values_tuple = tuple(current_values)
                        values_list.append(values_tuple)
                    except Exception as e:
                        print(f"Error preparing row for {table_name}: {e} - Row: {row_dict}")
                
                if values_list:
                    # print(f"Inserting {len(values_list)} rows into {table_name}...")
                    transaction.insert(table=table_name, columns=cols, values=values_list)
                    inserted_counts[table_name] = len(values_list)
                    total_rows_attempted += len(values_list)
                else:
                    inserted_counts[table_name] = 0
            else:
                inserted_counts[table_name] = 0
        # print(f"Transaction attempting to insert {total_rows_attempted} rows across all tables.") # Less verbose

    try:
        print("Executing data insertion transaction...")
        all_data_lists = [service_location_rows, customer_rows, equipment_rows_final, maintenance_job_rows, customer_equipment_assignment_rows]
        if any(len(data_list) > 0 for data_list in all_data_lists):
            db_instance.run_in_transaction(insert_data_txn)
            print("Transaction committed successfully.")
            for table, count in inserted_counts.items():
                if count > 0: print(f"  -> Inserted {count} rows into {table}.")
            return True
        else:
            print("No data prepared for insertion.")
            return True
    except exceptions.Aborted as e:
        print(f"ERROR: Data insertion transaction aborted: {e}. Consider retrying.")
        return False
    except Exception as e:
        print(f"ERROR during data insertion transaction: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        print("Data insertion failed. Database schema might exist but data is missing/incomplete.")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Spanner FleetPro Schema Setup Script...")
    start_time = time.time()

    if not PROJECT_ID:
        print("\nCRITICAL ERROR: GOOGLE_CLOUD_PROJECT environment variable not set. Aborting.")
        exit(1)
    

    # --- Step 1: Create schema ---
    if not setup_fleet_schema_and_indexes(database):
        print("\nAborting script due to errors during base schema/index creation.")
        exit(1)

    # --- Step 2: Create graph definition ---
    if not setup_fleet_graph_definition(database):
        print("\nAborting script due to errors during graph definition creation.")
        exit(1)

    # --- Step 3: Insert data into the base tables ---
    # Before inserting, you might want to clear existing data if this script is re-runnable
    # For now, it assumes tables are empty or 'IF NOT EXISTS' handles schema, but data is appended.
    # Consider adding a 'clear_data' function if needed, or run reset.sql manually.
    if not insert_fleet_data(database):
        print("\nScript finished with errors during data insertion.")
        exit(1)

    end_time = time.time()
    print("\n-----------------------------------------")
    print("Rouse FleetPro Spanner Setup Script finished successfully!")
    print(f"Database '{DATABASE_ID}' on instance '{INSTANCE_ID}' has been set up with the schema, graph, and sample data.")
    print(f"Total time: {end_time - start_time:.2f} seconds")
    print("-----------------------------------------")