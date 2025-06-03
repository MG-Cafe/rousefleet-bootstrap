import os
import requests
import json
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

load_dotenv()

BASE_URL = os.environ.get("ROUSEFLEET_BASE_URL")

#REPLACE ME to log Maintenance Request


def log_maintenance_request(
    equipment_serial_number: str,
    reported_by: str,
    issue_description: str,
    urgency: str,
    base_url: str = BASE_URL
):
    """
    Logs a new maintenance request for specified equipment in the Rouse FleetPro system.

    Args:
        equipment_serial_number: The serial number of the equipment.
        reported_by: Identifier for who is reporting (e.g., 'MarketResearchAgent', 'SystemUser').
        issue_description: Detailed description of the observed or suspected maintenance issue.
        urgency: Urgency level of the request (e.g., 'High', 'Medium', 'Low').
        base_url (str, optional): The base URL of the API. Defaults to BASE_URL.

    Returns:
         dict: The JSON response from the API if the request is successful or error details).
    """
    
    url = f"{base_url}/maintenance-requests"
    headers = {"Content-Type": "application/json"}
    payload = {
    "equipment_serial_number": equipment_serial_number,
    "job_description": issue_description,
    "service_type": urgency
}
    
    try:
        response = requests.post(url, headers=headers, json=payload) 
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print(f"Successfully Logged Maintenance Request. Status Code: {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating Log: {e}")
        # Optionally re-raise the exception if the caller needs to handle it
        # raise e
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}. Response text: {response.text}")
        return None
#REPLACE ME to update equipment location


def update_equipment_location(
    equipment_id: str,
    new_city: str,  # required
    new_address: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    notes: Optional[str] = None,
    base_url: str = BASE_URL
):
    """
    Updates the current location of a specified piece of equipment in the Rouse FleetPro system.

    Args:
        equipment_id: The unique ID of the equipment to update.
        new_city: The new city for the equipment.
        new_address: (Optional) The new full street address.
        latitude: (Optional) The new latitude.
        longitude: (Optional) The new longitude.
        notes: (Optional) Notes regarding the location update.
        base_url (str, optional): The base URL of the API. Defaults to BASE_URL.
    Returns:
       dict: The JSON response from the API if the request is successful or has errors.
    """
    if latitude is not None:
        latitude = float(latitude)
    if longitude is not None:
        longitude = float(longitude)

 
    url = f"{base_url}/equipment/{equipment_id}/location"
    headers = {"Content-Type": "application/json"}
    payload = {
        "new_city": new_city,
        "new_address": new_address,
        "latitude": latitude,
        "longitude": longitude,
        "notes": notes
    }
    # Remove entries where value is None, so they aren't sent as null unless intended by API
    payload = {k: v for k, v in payload.items() if v is not None}

    if not payload.get("new_city") and not payload.get("new_address"): # Should always have new_city now
        msg = "Client validation: new_city (or at least new_address) is required by the tool's intent."
        print(f"MCP Client: Error - {msg}")
        return {"error": msg, "status_code": "VALIDATION_ERROR"}

    print(f"MCP Client: Attempting POST to: {url} with payload: {payload}")
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"MCP Client: Successfully updated equipment location. Status: {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating event registration: {e}")
        # Optionally re-raise the exception if the caller needs to handle it
        # raise e
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}. Response text: {response.text}")
        return None