from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, stream_with_context, current_app
import json
import traceback
from datetime import datetime, timezone
import uuid

from fleet_advisor_agent_logic import call_dispatch_agent_for_recommendation, execute_dispatch_assignment



fleet_advisor_bp = Blueprint('fleet_advisor', __name__, template_folder='templates')

def get_form_data_for_advisor_page():
    equipment_categories = []
    equipment_makes = []
    try:
        from app import db as current_main_app_db, run_query as main_app_run_query

        if not current_main_app_db:
            current_app.logger.error("Error in get_form_data_for_advisor_page: main_app_db is not available.")
            return {"categories": [], "makes": []}

        cat_sql = "SELECT DISTINCT category FROM Equipment WHERE category IS NOT NULL ORDER BY category"
        cat_fields = ["category"]
        categories_result = main_app_run_query(sql=cat_sql, expected_fields=cat_fields)
        if categories_result:
            equipment_categories = [row['category'] for row in categories_result]

        make_sql = "SELECT DISTINCT make FROM Equipment WHERE make IS NOT NULL ORDER BY make"
        make_fields = ["make"]
        makes_result = main_app_run_query(sql=make_sql, expected_fields=make_fields)
        if makes_result:
            equipment_makes = [row['make'] for row in makes_result]

        return {"categories": equipment_categories, "makes": equipment_makes}

    except ImportError:
        current_app.logger.error("ERROR in get_form_data_for_advisor_page: Could not import db or run_query from app.py.", exc_info=True)
        return {"categories": [], "makes": []}
    except Exception as e:
        current_app.logger.error(f"Error fetching form data in fleet_advisor_routes: {e}", exc_info=True)
        return {"categories": [], "makes": []}

@fleet_advisor_bp.route('/dispatch-advisor', methods=['GET'])
def dispatch_advisor_form_page():
    form_data = get_form_data_for_advisor_page()
    current_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return render_template(
        'dispatch_advisor_form.html',
        categories=form_data.get("categories", []),
        makes=form_data.get("makes", []),
        current_date=current_date,
        title="Optimal Equipment Dispatch Advisor"
    )

@fleet_advisor_bp.route('/api/dispatch-advisor/submit', methods=['POST'])
def submit_dispatch_request():
    if request.method == 'POST':
        job_date = request.form.get('job_date')
        job_location = request.form.get('job_location')
        equipment_category = request.form.get('equipment_category')
        equipment_make = request.form.get('equipment_make', None)
        duration_days = request.form.get('duration_days', type=int, default=1)
        notes = request.form.get('notes', '')

        if not all([job_date, job_location, equipment_category]):
            flash('Please select a date, enter a job location, and choose an equipment category.', 'warning')
            return redirect(url_for('fleet_advisor.dispatch_advisor_form_page'))

        session['dispatch_request_params'] = {
            "job_date": job_date,
            "job_location": job_location,
            "equipment_category": equipment_category,
            "equipment_make": equipment_make if equipment_make else None,
            "duration_days": duration_days,
            "notes": notes,
            "requestor_name": "Dispatch User"
        }
        session.pop('dispatch_recommendation_details', None)
        current_app.logger.info(f"Dispatch Advisor Request Received, redirecting to review page. Params: {session['dispatch_request_params']}")
        return redirect(url_for('fleet_advisor.dispatch_advisor_review_page'))
    return redirect(url_for('fleet_advisor.dispatch_advisor_form_page'))

@fleet_advisor_bp.route('/dispatch-advisor/stream-recommendation')
def stream_dispatch_recommendation():
    try:
        from app import db
    except ImportError:
        db = None
    print("WARNING in fleet_advisor_routes: Could not import main_app_db from app.py at module level.")

    if not db:
        def error_stream_db_unavailable():
            error_payload = {"message": "Advisor service cannot connect to the database. Please try again later.", "code": "STREAM_DB_UNAVAILABLE_RECOMMEND"}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to database unavailability.'})}\n\n"
        return Response(stream_with_context(error_stream_db_unavailable()), mimetype='text/event-stream')

    dispatch_params = session.get('dispatch_request_params')
    if not dispatch_params:
        def error_stream_no_params():
            error_payload = {"message": "Missing dispatch parameters in session. Please submit the form again.", "code": "NO_DISPATCH_PARAMS"}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to missing parameters.'})}\n\n"
        return Response(stream_with_context(error_stream_no_params()), mimetype='text/event-stream')

    def generate_stream():
        current_app.logger.info(f"--- ADVISOR_SSE: generate_stream (recommendation) called for job at {dispatch_params.get('job_location')} ---")
        try:
            for event_data in call_dispatch_agent_for_recommendation(
                job_date=dispatch_params['job_date'],
                job_location=dispatch_params['job_location'],
                equipment_category=dispatch_params['equipment_category'],
                equipment_make=dispatch_params.get('equipment_make'),
                duration_days=dispatch_params['duration_days'],
                notes=dispatch_params.get('notes'),
                requestor_name=dispatch_params['requestor_name']
            ):
                event_type = event_data.get("type", "thought")
                data_to_send = event_data.get("data")
                try:
                    data_payload = json.dumps(data_to_send)
                except TypeError as te:
                    current_app.logger.error(f"!!! ADVISOR_SSE: TypeError serializing data for event '{event_type}': {te}. Data: {data_to_send}")
                    data_payload = json.dumps({"error": "Data serialization issue", "original_type": str(type(data_to_send))})
                    event_type = "thought_error"
                
                yield f"event: {event_type}\ndata: {data_payload}\n\n"

                if event_type == "recommendation_complete" or event_type == "error":
                    session['dispatch_recommendation_details'] = data_to_send
                    session.modified = True
                    current_app.logger.info(f"--- ADVISOR_SSE: Stored '{event_type}' data in session. ---")
            
            current_app.logger.info(f"--- ADVISOR_SSE: Agent recommendation loop finished. Yielding stream_end. ---")
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Recommendation stream finished.'})}\n\n"
        except Exception as e:
            error_details_str = traceback.format_exc()
            current_app.logger.error(f"!!! ADVISOR_SSE: UNHANDLED EXCEPTION during generate_stream (recommendation): {e}\n{error_details_str}")
            error_payload_data = {
                "message": f"Server error during recommendation generation: {str(e)}",
                "code": "RECOMMENDATION_STREAM_UNHANDLED_CRASH",
                "raw_output": error_details_str
            }
            yield f"event: error\ndata: {json.dumps(error_payload_data)}\n\n"
            session['dispatch_recommendation_details'] = error_payload_data
            session.modified = True
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream ended due to server error.'})}\n\n"
        finally:
            current_app.logger.info(f"--- ADVISOR_SSE: generate_stream function for recommendation ending. ---")
    return Response(stream_with_context(generate_stream()), mimetype='text/event-stream')

@fleet_advisor_bp.route('/dispatch-advisor/review', methods=['GET'])
def dispatch_advisor_review_page():
    recommendation_details = session.get('dispatch_recommendation_details')
    is_error_plan = False
    if isinstance(recommendation_details, dict):
        if recommendation_details.get("code") and "message" in recommendation_details:
            is_error_plan = True
        elif "error" in recommendation_details:
             is_error_plan = True
    return render_template('dispatch_advisor_review.html',
                           recommendation=recommendation_details,
                           is_error_plan=is_error_plan,
                           title="Review Dispatch Recommendation")

@fleet_advisor_bp.route('/api/dispatch-advisor/confirm-dispatch', methods=['POST'])
def confirm_dispatch_action():
    confirmed_recommendation_json_str = request.form.get('confirmed_recommendation_json')
    confirmed_recommendation = None
    if confirmed_recommendation_json_str:
        try:
            confirmed_recommendation = json.loads(confirmed_recommendation_json_str)
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Dispatch Confirm JSONDecodeError: {e}. Data: {confirmed_recommendation_json_str[:500]}")
            flash("Error parsing confirmed recommendation data. Please try again.", "danger")
            return redirect(url_for('fleet_advisor.dispatch_advisor_review_page'))

    if not confirmed_recommendation or \
       (isinstance(confirmed_recommendation, dict) and confirmed_recommendation.get("code") and "message" in confirmed_recommendation) or \
       (isinstance(confirmed_recommendation.get("data"), dict) and "error" in confirmed_recommendation.get("data")):
        flash("Cannot confirm an invalid or previously errored recommendation. Please generate a new one.", "danger")
        return redirect(url_for('fleet_advisor.dispatch_advisor_form_page'))

    equipment_id_to_dispatch = confirmed_recommendation.get("recommended_equipment_id")
    original_request_params = session.get('dispatch_request_params', {}) 

    if not equipment_id_to_dispatch:
        flash("Confirmed recommendation is missing the essential equipment ID. Please try again.", "danger")
        return redirect(url_for('fleet_advisor.dispatch_advisor_review_page'))

    session['dispatch_execution_params'] = {
        "user_name": original_request_params.get("requestor_name", "Dispatch User"),
        "equipment_id": equipment_id_to_dispatch,
        "equipment_details": confirmed_recommendation.get("equipment_details",{}),
        "job_details": { 
            "location": original_request_params.get("job_location"),
            "date": original_request_params.get("job_date"),
            "duration_days": original_request_params.get("duration_days"),
            "notes": original_request_params.get("notes")
        },
        "agent_session_user_id": str(uuid.uuid4())
    }
    current_app.logger.info(f"--- [DISPATCH_CONFIRM] Stored dispatch_execution_params for redirection. ---")
    session.pop('dispatch_recommendation_details', None)
    session.modified = True
    return redirect(url_for('fleet_advisor.dispatch_advisor_post_status_page'))

@fleet_advisor_bp.route('/dispatch-advisor/post-status', methods=['GET'])
def dispatch_advisor_post_status_page():
    if 'dispatch_execution_params' not in session:
        flash("No dispatch execution parameters found. Please confirm a recommendation first.", "warning")
        return redirect(url_for('fleet_advisor.dispatch_advisor_form_page'))

    exec_params = session['dispatch_execution_params']
    equipment_details = exec_params.get("equipment_details", {})
    equipment_desc = equipment_details.get("description", exec_params.get("equipment_id", "Selected Equipment"))
    title = f"Dispatch Status for: {equipment_desc}"
    
    return render_template(
        'dispatch_advisor_post_status.html',
        title=title,
    )

@fleet_advisor_bp.route('/dispatch-advisor/stream-post-status')
def stream_dispatch_post_status():
    try:
        from app import db
    except ImportError:
        db = None

    if not db:
        def error_stream_db_unavailable_post():
            error_payload = {"message": "Dispatch execution service cannot connect to database. Please try again later.", "code": "STREAM_POST_DB_UNAVAILABLE"}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to database unavailability.'})}\n\n"
        return Response(stream_with_context(error_stream_db_unavailable_post()), mimetype='text/event-stream')
    execution_params = session.get('dispatch_execution_params')
    if not execution_params:
        def error_stream_no_exec_params():
            error_payload = {"message": "Missing dispatch execution parameters in session. Please start over.", "code": "NO_EXEC_PARAMS"}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to missing execution parameters.'})}\n\n"
        return Response(stream_with_context(error_stream_no_exec_params()), mimetype='text/event-stream')

    user_name = execution_params.get("user_name", "Dispatch User")
    equipment_id = execution_params.get("equipment_id")
    job_details = execution_params.get("job_details", {})
    # Add this line to get the equipment details
    equipment_details = execution_params.get("equipment_details", {}) 
    agent_session_user_id = execution_params.get("agent_session_user_id", str(uuid.uuid4()))

    if not equipment_id or not job_details:
        def error_stream_bad_exec_data():
            error_payload = {"message": "Essential data (equipment_id or job_details) missing for dispatch execution.", "code": "BAD_EXEC_DATA"}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to incomplete execution data.'})}\n\n"
        return Response(stream_with_context(error_stream_bad_exec_data()), mimetype='text/event-stream')

    def generate_execute_events():
        try:
            current_app.logger.info(f"--- ADVISOR_POST_SSE: Starting dispatch execution for {user_name}, Equipment: {equipment_id} ---")
            for event in execute_dispatch_assignment(user_name, equipment_id, equipment_details, job_details, agent_session_user_id):
                if not isinstance(event, dict) or 'type' not in event or 'data' not in event:
                    current_app.logger.error(f"Malformed event from execute_dispatch_assignment: {event}")
                    malformed_event_info = {"type": "thought", "data": f"Agent (execute) produced a malformed event: {str(event)[:200]}"}
                    yield f"event: {malformed_event_info['type']}\ndata: {json.dumps(malformed_event_info['data'])}\n\n"
                    continue
                
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            
            current_app.logger.info(f"--- ADVISOR_POST_SSE: execute_dispatch_assignment finished successfully. ---")
            
            session.pop('dispatch_execution_params', None)
            session.pop('dispatch_request_params', None) 
            session.modified = True
            
            yield f"event: stream_end\ndata: {json.dumps({'message': 'Dispatch execution stream finished successfully.'})}\n\n"

        except Exception as e:
            error_details_str = traceback.format_exc()
            current_app.logger.error(f"!!! ADVISOR_POST_SSE: UNHANDLED EXCEPTION in generate_execute_events (post_status): {e}\n{error_details_str}")
            
            error_payload = {
                "message": f"A critical server error occurred during dispatch execution: {str(e)}",
                "code": "EXECUTE_STREAM_UNHANDLED_CRASH",
                "raw_output": error_details_str
            }
            try:
                yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            except Exception as yield_err:
                current_app.logger.error(f"Failed to yield error event to client (post-status): {yield_err}")
            
            try:
                yield f"event: stream_end\ndata: {json.dumps({'message': 'Stream closed due to critical server error.'})}\n\n"
            except Exception as yield_close_err:
                current_app.logger.error(f"Failed to yield stream_closed event after error (post-status): {yield_close_err}")

    return Response(stream_with_context(generate_execute_events()), mimetype='text/event-stream')