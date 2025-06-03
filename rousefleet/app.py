# app.py (Updated with fleet_advisor_bp registration)

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, abort, flash, request, jsonify, current_app
from google.cloud import spanner
from google.cloud.spanner_v1 import param_types
from google.api_core import exceptions
import humanize
import uuid
import traceback
from dateutil import parser as dateutil_parser

# --- Import your new blueprint ---
from fleet_advisor_routes import fleet_advisor_bp # <<< ADD THIS LINE

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_default_secret_key_for_fleetpro_dev")

# --- Register your new blueprint ---
app.register_blueprint(fleet_advisor_bp) # <<< ADD THIS LINE

load_dotenv()
# --- Spanner Configuration ---
INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID", "rousefleet-graph-instance")
DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID", "graphdb")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = os.environ.get("APP_PORT","8080") # Will be overridden by PORT in Cloud Run
Maps_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

if not PROJECT_ID:
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
if not Maps_API_KEY:
    print("Warning: Maps_API_KEY environment variable not set. Maps will not function.")

# --- Spanner Client Initialization ---
db = None
try:
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)
    print(f"Attempting to connect to Spanner: {instance.name}/databases/{database.name}")

    if not database.exists():
         print(f"Error: Database '{database.name}' does not exist in instance '{instance.name}'.")
         print("Please ensure the database and tables are created.")
         db = None
    else:
        print("Database connection check successful (database exists).")
        db = database

except exceptions.NotFound:
    print(f"Error: Spanner instance '{INSTANCE_ID}' not found in project '{PROJECT_ID}'.")
except Exception as e:
    print(f"An unexpected error occurred during Spanner initialization: {e}")
    traceback.print_exc()

def run_query(sql, params=None, param_types_map=None, expected_fields=None):
    if not db:
        print("Error in run_query: Database connection (db object) is not available.")
        # This ConnectionError will be caught by the updated fleet_advisor_agent_logic
        raise ConnectionError("Spanner database connection not initialized.")
    
    results_list = []
    # print(f"--- Executing SQL ---\nSQL: {sql}") # Verbose logging, uncomment for debugging
    # if params: print(f"Params: {params}")
    # print("----------------------")
    
    try:
        with db.snapshot() as snapshot:
            results = snapshot.execute_sql(sql, params=params, param_types=param_types_map)
            
            if not expected_fields:
                print("Warning in run_query: expected_fields not provided. Attempting dynamic lookup.")
                try:
                    # Ensure results object is not None and has fields attribute
                    if results and hasattr(results, 'fields'):
                        field_names = [field.name for field in results.fields]
                    else:
                        # Handle cases where results might not be as expected (e.g., DML in snapshot, though unlikely here)
                        print("Error in run_query: Could not determine field names from results (results object or fields attribute missing).")
                        return None # Indicate an error processing results
                except AttributeError as e:
                    print(f"Error in run_query: Could not determine field names (results.fields failed): {e}")
                    return None # Indicate an error processing results
            else:
                field_names = expected_fields

            for row_idx, row in enumerate(results): # Iterate safely
                if len(field_names) != len(row):
                     print(f"Warning in run_query: Mismatch field names ({len(field_names)}) vs row values ({len(row)}). Row {row_idx}: {row}")
                     continue # Skip malformed row
                results_list.append(dict(zip(field_names, row)))
            # print(f"Query successful, fetched {len(results_list)} rows.")
            
    except (exceptions.NotFound, exceptions.PermissionDenied, exceptions.InvalidArgument) as spanner_err:
        print(f"Spanner Error in run_query ({type(spanner_err).__name__}): {spanner_err}")
        # Flashing messages won't work for SSE, but logging is good.
        return None # Return None to indicate a handled Spanner query failure
        
    except ValueError as ve: # Catch ValueErrors from field processing or other logic
         print(f"ValueError in run_query (e.g., query processing): {ve}")
         traceback.print_exc() # Print traceback for ValueErrors too
         return None
         
    except ConnectionError as ce: # Specifically catch ConnectionError if db object became None unexpectedly
        print(f"ConnectionError in run_query: {ce}")
        traceback.print_exc()
        # Re-raise this specific one if we want fleet_advisor_agent_logic to catch it explicitly
        # or return None to signal failure. For now, let it be caught by the general Exception below.
        # However, the initial 'if not db:' check should make this rare here.
        raise # Re-raise to be caught by the agent's specific ConnectionError handler if possible

    except Exception as e: # Catch any other unexpected exceptions
        print(f"An UNEXPECTED error occurred during query execution in run_query: {e}")
        traceback.print_exc() # Log the full traceback to server logs
        return None # MODIFIED: Return None instead of re-raising, to protect SSE streams
        
    return results_list

# --- FleetPro Data Access Functions ---

def get_all_equipment_db(limit=50):
    sql = """
        SELECT
            eq.equipment_id, eq.serial_number, eq.description, eq.category, eq.subcategory,
            eq.make, eq.model, eq.model_year, eq.meter_hours,
            eq.current_city, eq.current_state_province,
            c.customer_name AS current_customer_name, c.customer_id AS current_customer_id,
            sl.name AS current_service_location_name, sl.location_id AS current_service_location_id,
            eq.photo_url
        FROM Equipment AS eq
        LEFT JOIN Customer AS c ON eq.current_customer_id = c.customer_id
        LEFT JOIN ServiceLocation AS sl ON eq.current_service_location_id = sl.location_id
        ORDER BY eq.make, eq.model
        LIMIT @limit
    """
    params = {"limit": limit}
    param_types_map = {"limit": param_types.INT64}
    fields = [
        "equipment_id", "serial_number", "description", "category", "subcategory",
        "make", "model", "model_year", "meter_hours",
        "current_city", "current_state_province",
        "current_customer_name", "current_customer_id",
        "current_service_location_name", "current_service_location_id", "photo_url"
    ]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_equipment_details_db(equipment_id):
    sql = """
        SELECT
            eq.equipment_id, eq.serial_number, eq.description, eq.list_price,
            eq.meter_hours, eq.current_address, eq.current_city, eq.current_state_province,
            eq.current_postal_code, eq.current_country, eq.category, eq.subcategory,
            eq.make, eq.model, eq.model_year, eq.financing_eligible, eq.warranty_eligible,
            eq.photo_url, eq.video_url, eq.latitude, eq.longitude,
            eq.current_service_location_id, sl.name AS current_service_location_name,
            eq.current_customer_id, c.customer_name AS current_customer_name, c.industry_type AS customer_industry,
            eq.create_time
        FROM Equipment AS eq
        LEFT JOIN Customer AS c ON eq.current_customer_id = c.customer_id
        LEFT JOIN ServiceLocation AS sl ON eq.current_service_location_id = sl.location_id
        WHERE eq.equipment_id = @equipment_id
    """
    params = {"equipment_id": equipment_id}
    param_types_map = {"equipment_id": param_types.STRING}
    fields = [
        "equipment_id", "serial_number", "description", "list_price",
        "meter_hours", "current_address", "current_city", "current_state_province",
        "current_postal_code", "current_country", "category", "subcategory",
        "make", "model", "model_year", "financing_eligible", "warranty_eligible",
        "photo_url", "video_url", "latitude", "longitude",
        "current_service_location_id", "current_service_location_name",
        "current_customer_id", "current_customer_name", "customer_industry",
        "create_time"
    ]
    results = run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    return results[0] if results else None

def get_maintenance_jobs_for_equipment_db(equipment_id, limit=20):
    sql = """
        SELECT job_id, job_date, job_description, cost, service_type, create_time
        FROM MaintenanceJob
        WHERE equipment_id = @equipment_id
        ORDER BY job_date DESC
        LIMIT @limit
    """
    params = {"equipment_id": equipment_id, "limit": limit}
    param_types_map = {"equipment_id": param_types.STRING, "limit": param_types.INT64}
    fields = ["job_id", "job_date", "job_description", "cost", "service_type", "create_time"]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_customer_details_db(customer_id):
    sql = """
        SELECT customer_id, customer_name, industry_type, region, create_time
        FROM Customer
        WHERE customer_id = @customer_id
    """
    params = {"customer_id": customer_id}
    param_types_map = {"customer_id": param_types.STRING}
    fields = ["customer_id", "customer_name", "industry_type", "region", "create_time"]
    results = run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    return results[0] if results else None

def get_equipment_for_customer_db(customer_id, limit=50):
    sql = """
        SELECT
            eq.equipment_id, eq.serial_number, eq.description, eq.make, eq.model,
            asgn.assignment_type, asgn.assignment_start_date
        FROM Equipment AS eq
        JOIN CustomerEquipmentAssignment AS asgn ON eq.equipment_id = asgn.equipment_id
        WHERE asgn.customer_id = @customer_id
        ORDER BY eq.make, eq.model
        LIMIT @limit
    """
    params = {"customer_id": customer_id, "limit": limit}
    param_types_map = {"customer_id": param_types.STRING, "limit": param_types.INT64}
    fields = ["equipment_id", "serial_number", "description", "make", "model", "assignment_type", "assignment_start_date"]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_service_location_details_db(location_id):
    sql = """
        SELECT location_id, name, address, city, state_province, postal_code, country,
               latitude, longitude, capacity, create_time
        FROM ServiceLocation
        WHERE location_id = @location_id
    """
    params = {"location_id": location_id}
    param_types_map = {"location_id": param_types.STRING}
    fields = ["location_id", "name", "address", "city", "state_province", "postal_code", "country", "latitude", "longitude", "capacity", "create_time"]
    results = run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    return results[0] if results else None

def get_equipment_at_service_location_db(location_id, limit=50):
    sql = """
        SELECT
            equipment_id, serial_number, description, make, model, category, subcategory
        FROM Equipment
        WHERE current_service_location_id = @location_id
        ORDER BY make, model
        LIMIT @limit
    """
    params = {"location_id": location_id, "limit": limit}
    param_types_map = {"location_id": param_types.STRING, "limit": param_types.INT64}
    fields = ["equipment_id", "serial_number", "description", "make", "model", "category", "subcategory"]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_all_customers_db(limit=100):
    sql = """
        SELECT customer_id, customer_name, industry_type, region
        FROM Customer
        ORDER BY customer_name
        LIMIT @limit
    """
    params = {"limit": limit}
    param_types_map = {"limit": param_types.INT64}
    fields = ["customer_id", "customer_name", "industry_type", "region"]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_all_service_locations_db(limit=50):
    sql = """
        SELECT location_id, name, city, state_province, capacity
        FROM ServiceLocation
        ORDER BY name
        LIMIT @limit
    """
    params = {"limit": limit}
    param_types_map = {"limit": param_types.INT64}
    fields = ["location_id", "name", "city", "state_province", "capacity"]
    return run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)

def get_equipment_by_serial_number_db(serial_number):
    sql = "SELECT equipment_id FROM Equipment WHERE serial_number = @serial_number LIMIT 1"
    params = {"serial_number": serial_number}
    param_types_map = {"serial_number": param_types.STRING}
    fields = ["equipment_id"]
    results = run_query(sql, params=params, param_types_map=param_types_map, expected_fields=fields)
    return results[0]['equipment_id'] if results else None

def add_maintenance_job_db(equipment_id, job_description, cost, service_type, job_date=None):
    if not db: raise ConnectionError("DB not init.")
    job_id = str(uuid.uuid4())
    job_date_to_insert = job_date # Will be Python datetime object or None
    if job_date is None:
        job_date_to_insert = datetime.now(timezone.utc)
    elif isinstance(job_date, str):
        try:
            job_date_to_insert = dateutil_parser.isoparse(job_date)
        except ValueError:
            print(f"Invalid date string for job_date: {job_date}. Defaulting to now.")
            job_date_to_insert = datetime.now(timezone.utc)
    
    # Ensure timezone aware for Spanner
    if job_date_to_insert.tzinfo is None or job_date_to_insert.tzinfo.utcoffset(job_date_to_insert) is None:
        job_date_to_insert = job_date_to_insert.replace(tzinfo=timezone.utc)
    else:
        job_date_to_insert = job_date_to_insert.astimezone(timezone.utc)

    def _insert_job(transaction):
        transaction.insert(
            table="MaintenanceJob",
            columns=["job_id", "equipment_id", "job_date", "job_description", "cost", "service_type", "create_time"],
            values=[(job_id, equipment_id, job_date_to_insert, job_description, cost, service_type, spanner.COMMIT_TIMESTAMP)]
        )
    try:
        db.run_in_transaction(_insert_job)
        return job_id
    except Exception as e:
        print(f"Error inserting maintenance job for equipment {equipment_id}: {e}")
        traceback.print_exc()
        return None

def add_equipment_db(data):
    if not db: raise ConnectionError("DB not init.")
    equipment_id = str(uuid.uuid4())
    list_price = float(data.get("list_price", 0.0)) if data.get("list_price") is not None else None
    meter_hours = int(data.get("meter_hours", 0)) if data.get("meter_hours") is not None else None
    model_year = int(data.get("model_year")) if data.get("model_year") else None
    latitude = float(data.get("latitude", 0.0)) if data.get("latitude") is not None else None
    longitude = float(data.get("longitude", 0.0)) if data.get("longitude") is not None else None

    def _insert_equipment(transaction):
        transaction.insert(
            table="Equipment",
            columns=[
                "equipment_id", "serial_number", "description", "list_price", "meter_hours",
                "current_address", "current_city", "current_state_province", "current_postal_code", "current_country",
                "category", "subcategory", "make", "model", "model_year",
                "financing_eligible", "warranty_eligible", "photo_url", "video_url",
                "latitude", "longitude", "current_service_location_id", "current_customer_id", "create_time"
            ],
            values=[(
                equipment_id, data["serial_number"], data["description"], list_price, meter_hours,
                data.get("current_address"), data.get("current_city"), data.get("current_state_province"),
                data.get("current_postal_code"), data.get("current_country"),
                data["category"], data.get("subcategory"), data["make"], data["model"], model_year,
                bool(data.get("financing_eligible", False)), bool(data.get("warranty_eligible", False)),
                data.get("photo_url"), data.get("video_url"),
                latitude, longitude,
                data.get("current_service_location_id"), data.get("current_customer_id"),
                spanner.COMMIT_TIMESTAMP
            )]
        )
    try:
        db.run_in_transaction(_insert_equipment)
        return equipment_id
    except Exception as e:
        print(f"Error inserting equipment (serial: {data.get('serial_number')}): {e}")
        traceback.print_exc()
        return None

# --- Custom Jinja Filter ---
@app.template_filter('humanize_datetime')
def _jinja2_filter_humanize_datetime(value, default="just now"):
    if not value: return default
    dt_object = None
    if isinstance(value, str):
        try: dt_object = dateutil_parser.isoparse(value)
        except (ValueError, TypeError):
            app.logger.warning(f"Could not parse date string '{value}' in humanize_datetime. Trying generic parser.")
            try: dt_object = dateutil_parser.parse(value)
            except (dateutil_parser.ParserError, TypeError, OverflowError) as e2: # Catch more errors
                 app.logger.error(f"Generic parse also failed for '{value}': {e2}")
                 return str(value)
    elif isinstance(value, datetime):
        dt_object = value
    else: return str(value)

    if dt_object is None: return str(value) # Should not happen if parsing was successful

    now = datetime.now(timezone.utc)
    if dt_object.tzinfo is None or dt_object.tzinfo.utcoffset(dt_object) is None:
        dt_object = dt_object.replace(tzinfo=timezone.utc)
    else:
        dt_object = dt_object.astimezone(timezone.utc)
    try:
        return humanize.naturaltime(now - dt_object)
    except TypeError: return dt_object.strftime("%Y-%m-%d %H:%M UTC")

# --- FleetPro Routes ---
@app.route('/')
def home():
    all_equipment = []
    current_time = datetime.utcnow() # For footer year
    if not db:
        flash("Database connection not available. Cannot load equipment data.", "danger")
    else:
        try:
            all_equipment = get_all_equipment_db(limit=100)
        except Exception as e:
             flash(f"Failed to load equipment data: {e}", "danger")
             print(f"Error in home route: {e}")
             traceback.print_exc()
    return render_template('fleet_index.html', equipment_list=all_equipment, title="Fleet Overview", now=current_time)

@app.route('/equipment/<string:equipment_id>')
def equipment_detail(equipment_id):
    equipment = None
    maintenance_jobs = []
    current_time = datetime.utcnow()
    if not db:
        flash("Database connection not available.", "danger")
        abort(503)
    try:
        equipment = get_equipment_details_db(equipment_id)
        if not equipment: abort(404)
        maintenance_jobs = get_maintenance_jobs_for_equipment_db(equipment_id)
        if equipment.get("latitude") is not None: equipment["latitude"] = float(equipment["latitude"])
        if equipment.get("longitude") is not None: equipment["longitude"] = float(equipment["longitude"])
    except Exception as e:
        flash(f"Failed to load equipment details: {e}", "danger")
        print(f"Error loading equipment {equipment_id}: {e}")
        traceback.print_exc()
        return render_template('equipment_detail.html', equipment=None, maintenance_jobs=[], error=True, Maps_api_key=Maps_API_KEY, title="Equipment Error", now=current_time)
    return render_template('equipment_detail.html', equipment=equipment, maintenance_jobs=maintenance_jobs, Maps_api_key=Maps_API_KEY, title=f"Equipment: {equipment.get('make','')} {equipment.get('model','')}", now=current_time)

@app.route('/customer/<string:customer_id>')
def customer_detail(customer_id):
    customer = None
    assigned_equipment = []
    current_time = datetime.utcnow()
    if not db:
        flash("Database connection not available.", "danger")
        abort(503)
    try:
        customer = get_customer_details_db(customer_id)
        if not customer: abort(404)
        assigned_equipment = get_equipment_for_customer_db(customer_id)
    except Exception as e:
        flash(f"Failed to load customer details: {e}", "danger")
        return render_template('customer_detail.html', customer=None, assigned_equipment=[], error=True, title="Customer Error", now=current_time)
    return render_template('customer_detail.html', customer=customer, assigned_equipment=assigned_equipment, title=f"Customer: {customer.get('customer_name','')}", now=current_time)

@app.route('/location/<string:location_id>')
def service_location_detail(location_id):
    location = None
    equipment_at_location = []
    current_time = datetime.utcnow()
    if not db:
        flash("Database connection not available.", "danger")
        abort(503)
    try:
        location = get_service_location_details_db(location_id)
        if not location: abort(404)
        equipment_at_location = get_equipment_at_service_location_db(location_id)
        if location.get("latitude") is not None: location["latitude"] = float(location["latitude"])
        if location.get("longitude") is not None: location["longitude"] = float(location["longitude"])
    except Exception as e:
        flash(f"Failed to load service location details: {e}", "danger")
        return render_template('location_detail.html', location=None, equipment_at_location=[], error=True, Maps_api_key=Maps_API_KEY, title="Location Error", now=current_time)
    return render_template('location_detail.html', location=location, equipment_at_location=equipment_at_location, Maps_api_key=Maps_API_KEY, title=f"Location: {location.get('name', '')}", now=current_time)

@app.route('/customers')
def customers_list():
    all_customers = []
    current_time = datetime.utcnow()
    if not db: flash("Database not connected.", "danger")
    else:
        try: all_customers = get_all_customers_db()
        except Exception as e: flash(f"Error fetching customers: {e}", "danger")
    return render_template('customers_list.html', customers=all_customers, title="All Customers", now=current_time)

@app.route('/locations')
def service_locations_list():
    all_locations = []
    current_time = datetime.utcnow()
    if not db: flash("Database not connected.", "danger")
    else:
        try: all_locations = get_all_service_locations_db()
        except Exception as e: flash(f"Error fetching locations: {e}", "danger")
    return render_template('locations_list.html', locations=all_locations, title="All Service Locations", now=current_time)

# --- FleetPro API Endpoints ---
@app.route('/api/maintenance-requests', methods=['POST'])
def add_maintenance_job_api():
    if not db: return jsonify({"error": "Database connection unavailable"}), 503
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    required_fields = ["equipment_serial_number", "job_description", "service_type"]
    if not all(field in data and data[field] for field in required_fields): # Check for presence and non-empty
        return jsonify({"error": f"Missing or empty required fields: {', '.join(required_fields)}"}), 400

    equipment_id = get_equipment_by_serial_number_db(data["equipment_serial_number"])
    if not equipment_id:
        return jsonify({"error": f"Equipment with serial number '{data['equipment_serial_number']}' not found"}), 404
    
    cost = float(data.get("cost", 0.0) or 0.0) 
    job_date_str = data.get("job_date") 

    job_id = add_maintenance_job_db(equipment_id, data["job_description"], cost, data["service_type"], job_date_str)
    if job_id:
        return jsonify({"message": "Maintenance job added successfully", "job_id": job_id}), 201
    else:
        return jsonify({"error": "Failed to save maintenance job"}), 500

@app.route('/api/equipment', methods=['POST'])
def add_equipment_api():
    if not db: return jsonify({"error": "Database connection unavailable"}), 503
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    required_fields = ["serial_number", "description", "category", "make", "model"]
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": f"Missing or empty required fields: {', '.join(required_fields)}"}), 400
    existing_equipment_id = get_equipment_by_serial_number_db(data["serial_number"])
    if existing_equipment_id:
        return jsonify({"error": f"Equipment with serial number '{data['serial_number']}' already exists."}), 409

    equipment_id = add_equipment_db(data)
    if equipment_id:
        return jsonify({"message": "Equipment added successfully", "equipment_id": equipment_id}), 201
    else:
        return jsonify({"error": "Failed to save equipment"}), 500

# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', title="Page Not Found", now=datetime.utcnow()), 404

@app.errorhandler(500)
def internal_server_error(e):
    print(f"Internal Server Error: {e}")
    traceback.print_exc()
    return render_template('500.html', title="Server Error", now=datetime.utcnow()), 500

@app.errorhandler(503)
def service_unavailable(e):
    print(f"Service Unavailable Error: {e}") # For logging
    return render_template('503.html', title="Service Unavailable", now=datetime.utcnow()), 503

# --- Context Processors ---
@app.context_processor
def inject_now():
    """Injects current UTC datetime into all templates as 'now' for footer year."""
    return {'now': datetime.utcnow()}


@app.route('/api/equipment/<string:equipment_id>/location', methods=['POST'])
def api_update_equipment_location(equipment_id):
    if not db:
        current_app.logger.error("API Update Location: Database connection not available.")
        return jsonify({"error": "Database connection not available"}), 503
    
    data = request.get_json()
    if not data:
        current_app.logger.error(f"API Update Location for {equipment_id}: Invalid JSON payload.")
        return jsonify({"error": "Invalid JSON payload"}), 400

    new_city = data.get('new_city')
    new_address = data.get('new_address')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    notes = data.get('notes', '') # Optional notes

    if not new_city and not new_address: # At least city or address should be provided
        current_app.logger.error(f"API Update Location for {equipment_id}: Missing new_city or new_address.")
        return jsonify({"error": "Missing required location fields: new_city or new_address"}), 400

    # Validate latitude and longitude if provided
    if latitude is not None:
        try:
            latitude = float(latitude)
        except (ValueError, TypeError):
            current_app.logger.error(f"API Update Location for {equipment_id}: Invalid latitude value '{latitude}'.")
            return jsonify({"error": "Invalid latitude value. Must be a number."}), 400
    
    if longitude is not None:
        try:
            longitude = float(longitude)
        except (ValueError, TypeError):
            current_app.logger.error(f"API Update Location for {equipment_id}: Invalid longitude value '{longitude}'.")
            return jsonify({"error": "Invalid longitude value. Must be a number."}), 400

    try:
        def update_location_txn(transaction):
            # Check if equipment exists
            equipment_row = list(transaction.read(
                table='Equipment',
                columns=['equipment_id'],
                keyset=spanner.KeySet(keys=[[equipment_id]]),
                limit=1
            ))
            if not equipment_row:
                return False # Indicate equipment not found

            # Prepare fields to update
            update_data = {}
            if new_city is not None: update_data['current_city'] = new_city
            if new_address is not None: update_data['current_address'] = new_address
            if latitude is not None: update_data['latitude'] = latitude
            if longitude is not None: update_data['longitude'] = longitude
            # Could add a field for 'location_update_notes' or append to description if desired

            if not update_data: # Should not happen due to earlier check, but as a safeguard
                 return True # No actual update needed, but not an error

            columns_to_update = list(update_data.keys())
            values_to_update = list(update_data.values())
            
            # Add equipment_id to identify the row
            columns_to_update.append('equipment_id')
            values_to_update.append(equipment_id)

            transaction.update(
                table='Equipment',
                columns=columns_to_update,
                values=[values_to_update]
            )
            return True # Indicate success

        success = db.run_in_transaction(update_location_txn)

        if not success:
            current_app.logger.warning(f"API Update Location: Equipment ID '{equipment_id}' not found.")
            return jsonify({"error": f"Equipment ID '{equipment_id}' not found"}), 404
        
        current_app.logger.info(f"Successfully updated location for equipment {equipment_id} via API.")
        return jsonify({"message": f"Location for equipment {equipment_id} updated successfully."}), 200

    except Exception as e:
        current_app.logger.error(f"Error updating equipment location via API for {equipment_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to update equipment location: {str(e)}"}), 500


if __name__ == '__main__':
    # For Cloud Run, honor the PORT environment variable.
    # Fallback to APP_PORT (from .env or default), then 8080.
    port = int(os.environ.get("PORT", os.environ.get("APP_PORT", "8080")))
    # Debug mode should be False in production. Controlled by FLASK_DEBUG env var.
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    if not db:
        print("\n--- Cannot start Flask app: Spanner database connection failed. ---")
        print("--- Please check GCP_PROJECT_ID, Spanner instance/database IDs, permissions, and network. ---")
    else:
        print(f"\n--- Starting Rouse FleetPro Flask Server ---")
        print(f"Mode: {'Development (Debug)' if debug_mode else 'Production'}")
        print(f"Listening on: http://{APP_HOST}:{port}")
        app.run(debug=debug_mode, host=APP_HOST, port=port)