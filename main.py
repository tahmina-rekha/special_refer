# main.py (for your 'special-referral-email' Cloud Run service)
import os
import json
import re # Import the re module for regular expressions
from flask import Flask, request, jsonify
from flask_cors import CORS # Import CORS
from datetime import datetime, timedelta # For date/time calculations
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# NEW: Import Firebase Admin SDK and Firestore
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

app = Flask(__name__)
CORS(app) # Enable CORS for your Flask app

# Initialize db as None initially
db = None

# --- Firebase Initialization ---
# Cloud Run provides default credentials for the service account.
if not firebase_admin._apps:
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully using Application Default Credentials.")
        db = firestore.client(database_id="book-appointment") # Use your named Firestore database
        print("Firestore client initialized for database 'book-appointment'.")
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize Firebase Admin SDK or Firestore client at startup: {e}")
        raise
else:
    try:
        db = firestore.client(database_id="book-appointment")
        print("Firestore client initialized for database 'book-appointment'.")
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to obtain Firestore client when Firebase app already initialized: {e}")
        raise

# --- Global variable for app_id (provided by Canvas environment) ---
app_id = os.environ.get('APP_ID', 'default-app-id')

# --- SMTP Configuration (retrieved from environment variables) ---
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'niljoshna28@gmail.com')

# --- Hardcoded Specialist Details ---
# These are now hardcoded as per your request, and not passed from the agent.
SPECIALIST_EMAIL = "niljoshna28@gmail.com"
REFERRING_DOCTOR_NAME = "Lee Paul"

# --- Helper function for sending email via SMTP ---
def send_email_via_smtp(to_email, subject, plain_text_content, html_content):
    """
    Attempts to send an email via SMTP using the configured environment variables.
    Returns (True, message) on success, (False, error_message) on failure.
    """
    if not all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        print("SMTP credentials or sender email not fully configured. Cannot send real email.")
        return False, "SMTP credentials missing or incomplete in environment variables."

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject

        part1 = MIMEText(plain_text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        
        print(f"SMTP email sent successfully to {to_email}")
        return True, "Email sent successfully via SMTP."

    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP Authentication Error: Check username/password for {SMTP_USERNAME}. Error: {e}")
        return False, f"SMTP authentication failed: {str(e)}. Please check SMTP username and password."
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: Check host/port for {SMTP_HOST}:{SMTP_PORT}. Error: {e}")
        return False, f"SMTP connection failed: {str(e)}. Please check SMTP host and port."
    except Exception as e:
        print(f"An unexpected error occurred while sending email via SMTP: {e}")
        return False, f"An unexpected error occurred during email send: {str(e)}"

# --- Helper function to save appointment details to Firestore ---
def save_appointment_to_firestore(appointment_details, collection_name="specialist_appointments"):
    """
    Saves appointment details to a Firestore collection.
    Collection path: /artifacts/{appId}/public/data/{collection_name}
    """
    if db is None:
        print("ERROR: Firestore client (db) is not initialized. Cannot save appointment.")
        return False, "Firestore client not initialized."

    try:
        collection_path = f"artifacts/{app_id}/public/data/{collection_name}"
        doc_ref = db.collection(collection_path).document(appointment_details['appointment_id'])
        
        appointment_details['timestamp'] = firestore.SERVER_TIMESTAMP

        doc_ref.set(appointment_details)
        print(f"Appointment {appointment_details['appointment_id']} saved to Firestore at {collection_path}.")
        return True, "Appointment saved to database."
    except Exception as e:
        print(f"Error saving appointment to Firestore: {e}")
        return False, f"Failed to save appointment to database: {str(e)}"

# --- Helper function to manage patient profiles (UPDATED TO QUERY BY FIELD AND USE PATIENT_ID AS DOC ID FOR NEW) ---
def save_or_update_patient_profile(patient_data):
    """
    Saves or updates a patient profile in the 'patients' collection.
    If a profile with the given patient_id field exists, it updates it.
    Otherwise, it creates a new document using the provided patient_id as the document ID.
    """
    if db is None:
        print("ERROR: Firestore client (db) is not initialized. Cannot save patient profile.")
        return False, "Firestore client not initialized."

    try:
        patients_collection_path = f"artifacts/{app_id}/public/data/patients"
        
        # Query for the document where the 'patient_id' field matches
        # This is correct for finding an existing patient by their patient_id field
        query_ref = db.collection(patients_collection_path).where('patient_id', '==', patient_data['patient_id']).limit(1)
        docs = query_ref.stream()
        
        existing_doc = None
        for doc in docs:
            existing_doc = doc
            break # Get the first (and should be only) matching document

        if existing_doc:
            # Logic for updating an existing profile
            existing_data = existing_doc.to_dict()
            updated_data = {
                "last_updated": firestore.SERVER_TIMESTAMP
            }
            # Only update fields if they are provided and different from existing
            if patient_data.get('name') and patient_data['name'] != existing_data.get('name'):
                updated_data['name'] = patient_data['name']
            if patient_data.get('email') and patient_data['email'] != existing_data.get('email'):
                updated_data['email'] = patient_data['email']
            if patient_data.get('date_of_birth') and patient_data['date_of_birth'] != existing_data.get('date_of_birth'):
                updated_data['date_of_birth'] = patient_data['date_of_birth']
            if patient_data.get('phone_number') and patient_data['phone_number'] != existing_data.get('phone_number'):
                updated_data['phone_number'] = patient_data['phone_number']
            if patient_data.get('address') and patient_data['address'] != existing_data.get('address'):
                updated_data['address'] = patient_data['address']
            
            if updated_data: # Only update if there are changes
                doc_ref = db.collection(patients_collection_path).document(existing_doc.id) # Use actual document ID
                doc_ref.update(updated_data)
                print(f"Patient profile {patient_data['patient_id']} updated. Document ID: {existing_doc.id}")
            else:
                print(f"Patient profile {patient_data['patient_id']} exists, no new data to update. Document ID: {existing_doc.id}")
            return True, "Patient profile updated."
        else:
            # Logic for creating a new profile: use patient_id as the document ID
            if not patient_data.get('patient_id'):
                print("ERROR: Cannot create new patient profile. 'patient_id' is missing from patient_data.")
                return False, "Cannot create new patient profile: 'patient_id' is missing."

            new_doc_id = patient_data['patient_id'] # Use the provided patient_id as the document ID
            new_doc_ref = db.collection(patients_collection_path).document(new_doc_id)
            
            # This is a safeguard: if a document with this exact ID already exists
            # (e.g., if patient_id was previously used as doc ID directly),
            # we should update it instead of trying to create a duplicate.
            if new_doc_ref.get().exists:
                print(f"Warning: Document with ID '{new_doc_id}' already exists. Attempting to update it instead of creating new.")
                existing_data = new_doc_ref.get().to_dict()
                merged_data = {**existing_data, **patient_data}
                merged_data["last_updated"] = firestore.SERVER_TIMESTAMP
                new_doc_ref.set(merged_data) # Use set to overwrite/merge
                print(f"Patient profile {patient_data['patient_id']} updated (merged existing data at document ID {new_doc_id}).")
                return True, "Patient profile updated."

            patient_data['created_at'] = firestore.SERVER_TIMESTAMP
            patient_data['last_updated'] = firestore.SERVER_TIMESTAMP
            new_doc_ref.set(patient_data) # Create the new document with patient_id as its ID
            print(f"New patient profile {patient_data['patient_id']} created. Document ID: {new_doc_id}")
            return True, "New patient profile created."
    except Exception as e:
        print(f"Error saving/updating patient profile to Firestore: {e}")
        return False, f"Failed to save/update patient profile: {str(e)}"

# --- Helper function to get patient profile from Firestore (UPDATED TO QUERY BY FIELD) ---
def get_patient_profile_from_firestore(patient_id):
    """
    Retrieves a patient's profile from the 'patients' collection by querying on the 'patient_id' field.
    Returns (patient_data_dict, True) if found, (None, False) if not found or error.
    """
    if db is None:
        print("ERROR: Firestore client (db) is not initialized. Cannot retrieve patient profile.")
        return None, False

    try:
        patients_collection_path = f"artifacts/{app_id}/public/data/patients"
        
        # Query for the document where the 'patient_id' field matches
        query_ref = db.collection(patients_collection_path).where('patient_id', '==', patient_id).limit(1)
        docs = query_ref.stream()

        for doc in docs:
            print(f"Patient profile found for ID: {patient_id}. Document ID: {doc.id}")
            return doc.to_dict(), True
        
        print(f"No patient profile found for ID: {patient_id} in the 'patient_id' field.")
        return None, False
    except Exception as e:
        print(f"Error retrieving patient profile from Firestore: {e}")
        return None, False

# --- NEW ENDPOINT: Get GP Doctor Name from Appointments Collection ---
@app.route('/get_gp_doctor', methods=['POST'])
def get_gp_doctor_backend():
    """
    Retrieves the doctor's name from the most recent GP appointment in Firestore
    for a given patient_id.
    """
    if db is None:
        return jsonify({"success": False, "message": "Firestore client not initialized."}), 500
    
    try:
        request_data = request.get_json()
        patient_id = get_string_param(request_data, 'patient_id')

        if not patient_id:
            return jsonify({"success": False, "message": "Patient ID is required."}), 400

        appointments_collection_path = f"artifacts/{app_id}/public/data/appointments"
        
        # Query for GP appointments for the patient, ordered by timestamp descending
        # NOTE: Firestore does not support orderBy on multiple fields without an index.
        # We will fetch all and sort in Python.
        query_ref = db.collection(appointments_collection_path).where('patient_id', '==', patient_id)
        # Add a filter for 'GP' appointment type if desired, but it requires an index
        # query_ref = query_ref.where('appointment_type', '==', 'GP')

        docs = query_ref.stream() # Get all matching documents

        gp_appointments = []
        for doc in docs:
            data = doc.to_dict()
            # Filter for GP appointments and valid timestamps in Python
            if data.get('appointment_type') == 'GP' and 'timestamp' in data:
                gp_appointments.append(data)
        
        # Sort appointments by timestamp in descending order (most recent first)
        gp_appointments.sort(key=lambda x: x['timestamp'], reverse=True)

        doctor_name = None
        if gp_appointments:
            doctor_name = gp_appointments[0].get('doctor_name')
            if doctor_name == "a GP doctor": # If it's the generic placeholder, treat as not found
                doctor_name = None
            print(f"Found GP doctor '{doctor_name}' for patient ID: {patient_id}")
        else:
            print(f"No GP doctor found for patient ID: {patient_id}")

        return jsonify({
            "success": doctor_name is not None,
            "doctor_name": doctor_name,
            "message": "GP doctor retrieved successfully." if doctor_name else "No GP doctor found for this patient."
        }), 200

    except Exception as e:
        print(f"Error retrieving GP doctor: {e}")
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500


# --- Helper function to safely extract string values from potentially nested dictionaries ---
def get_string_param(data_dict, key, default_value=None):
    value = data_dict.get(key)
    if isinstance(value, dict) and value:
        return list(value.values())[0] if value else default_value
    return value if value is not None else default_value

# --- Main route for the specialist referral email tool ---
@app.route('/send_referral_email', methods=['POST'])
def send_referral_email_backend():
    """
    Handles incoming POST requests from the AI agent to book a specialist appointment,
    send confirmation emails to both patient and hardcoded specialist, and store details to Firestore.
    This function corresponds to the 'refer_specialist' operationId in the OpenAPI spec.
    """
    try:
        request_data = request.get_json()
        
        # Extract parameters from the request
        patient_id = get_string_param(request_data, 'patient_id', 'N/A')
        patient_name_from_request = get_string_param(request_data, 'patient_name')
        # recipient_email is now hardcoded
        # referring_doctor is now hardcoded
        treatment_details = get_string_param(request_data, 'treatment_details')
        urgent = request_data.get('urgent', False)

        symptoms = get_string_param(request_data, 'symptoms', 'unspecified symptoms')
        duration_value = request_data.get('duration_value')
        duration_unit = get_string_param(data_dict=request_data, key='duration_unit')

        # --- Retrieve patient profile from Firestore using patient_id ---
        patient_profile = None
        final_patient_name = None
        final_patient_email = None

        if patient_id and patient_id != 'N/A':
            patient_profile, profile_found = get_patient_profile_from_firestore(patient_id)
            
            if not profile_found:
                print(f"Warning: Patient profile not found for ID: {patient_id}. Attempting to create new patient profile.")
                # If profile not found, use the name from the request and generate a new ID if 'N/A'
                if patient_id == 'N/A': # Only generate new ID if it was N/A initially
                    patient_id = f"PATIENT_{os.urandom(4).hex()}"
                    print(f"Generated new patient ID: {patient_id}")
                final_patient_name = patient_name_from_request
                final_patient_email = None # No email from DB, so it's None initially
            else:
                # Profile found: Validate name and determine final name/email
                db_patient_name = patient_profile.get('name')
                db_patient_email = patient_profile.get('email')

                # Validate if patient_name_from_request matches db_patient_name (if both exist)
                if patient_name_from_request and db_patient_name and patient_name_from_request.lower() != db_patient_name.lower():
                    print(f"ERROR: Name mismatch for Patient ID '{patient_id}'. Request name: '{patient_name_from_request}', DB name: '{db_patient_name}'.")
                    return jsonify({
                        "success": False,
                        "message": f"Patient name '{patient_name_from_request}' does not match the name '{db_patient_name}' registered for Patient ID '{patient_id}'. Please verify."
                    }), 400
                
                # Determine final patient name: Prioritize DB name if found, otherwise use request name
                final_patient_name = db_patient_name if db_patient_name else patient_name_from_request
                # Determine final patient email: Prioritize DB email if found
                final_patient_email = db_patient_email

        else: # No patient_id provided by agent, so generate a new one
            patient_id = f"PATIENT_{os.urandom(4).hex()}"
            print(f"Generated new patient ID: {patient_id}")
            final_patient_name = patient_name_from_request
            final_patient_email = None # No email from DB, so it's None initially


        # Prepare patient data for saving/updating in the patient profile database
        # Use the name from the current request to ensure the latest name is persisted, if available.
        # Otherwise, use the final_patient_name determined above.
        name_to_save_in_profile = patient_name_from_request if patient_name_from_request else final_patient_name
        patient_profile_data_to_save = {
            "patient_id": patient_id,
            "name": name_to_save_in_profile, 
            "email": final_patient_email, 
            # Add other fields like 'date_of_birth', 'phone_number', 'address' here if collected
        }
        patient_profile_data_to_save = {k: v for k, v in patient_profile_data_to_save.items() if v is not None}

        # Save or update the patient profile in Firestore
        if patient_profile_data_to_save:
            profile_save_success, profile_save_message = save_or_update_patient_profile(patient_profile_data_to_save)
            if not profile_save_success:
                print(f"Warning: Failed to save/update patient profile: {profile_save_message}")

        # --- Input Validation ---
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        
        # DEBUG PRINTS START
        print(f"DEBUG: final_patient_name: '{final_patient_name}' (type: {type(final_patient_name)})")
        print(f"DEBUG: treatment_details: '{treatment_details}' (type: {type(treatment_details)})")
        print(f"DEBUG: All required fields check: {all([final_patient_name, treatment_details])}") # Removed recipient_email, referring_doctor
        print(f"DEBUG: Specialist email regex match: {re.match(email_regex, SPECIALIST_EMAIL) is not None}")
        # DEBUG PRINTS END

        missing_fields = []
        if not final_patient_name:
            missing_fields.append("patient_name")
        if not treatment_details:
            missing_fields.append("treatment_details")
        # recipient_email and referring_doctor are now hardcoded, so no need to check if they are missing from input

        if missing_fields:
            error_message = f"Missing required referral details: {', '.join(missing_fields)}."
            print(f"ERROR: {error_message}")
            return jsonify({"success": False, "message": error_message}), 400
        
        # Validate hardcoded specialist email
        if not isinstance(SPECIALIST_EMAIL, str) or not re.match(email_regex, SPECIALIST_EMAIL):
            print(f"CRITICAL ERROR: Hardcoded specialist email format is invalid: '{SPECIALIST_EMAIL}'")
            return jsonify({"success": False, "message": "Internal configuration error: Invalid specialist email format."}), 500
        
        # Validate patient email only if a final_patient_email is determined
        if final_patient_email and (not isinstance(final_patient_email, str) or not re.match(email_regex, final_patient_email)):
            print(f"ERROR: Invalid patient email format from database: '{final_patient_email}'")
            return jsonify({"success": False, "message": "Invalid patient email format from database."}), 400 # Changed message

        # --- Assign Specialist Appointment Date/Time ---
        assigned_date = None
        assigned_time = "09:00"
        appointment_type = "Specialist"

        now = datetime.now()
        if duration_value is not None and duration_unit:
            if duration_unit == 'days' and duration_value <= 7:
                assigned_date = now + timedelta(weeks=2)
                assigned_time = "10:00"
            elif duration_unit == 'weeks' and duration_value <= 4:
                assigned_date = now + timedelta(weeks=3)
                assigned_time = "14:00"
            elif (duration_unit == 'months' and duration_value >= 1) or (duration_unit == 'weeks' and duration_value > 4):
                assigned_date = now + timedelta(weeks=6)
                assigned_time = "11:00"
            else:
                assigned_date = now + timedelta(weeks=3)
                assigned_time = "09:30"
        else:
            assigned_date = now + timedelta(weeks=3)
            assigned_time = "09:00"
        
        final_appointment_date = assigned_date.strftime('%Y-%m-%d')
        final_appointment_time = assigned_time

        # --- Generate Appointment ID ---
        appointment_id = f"SPEC-{patient_id.replace('N/A', 'UNKNOWN')[:5]}-{os.urandom(3).hex()}"

        patient_history = "No detailed history available." # Placeholder since function is removed
        history_retrieved_success = False
        
        # --- Construct Specialist Email Content ---
        urgency_prefix = "URGENT: " if urgent else ""
        specialist_subject = f"{urgency_prefix}Specialist Referral for {final_patient_name} (Patient ID: {patient_id})"
        
        specialist_plain_text_body = (
            f"Dear Specialist/Referral Department,\n\n"
            f"This is a referral for patient {final_patient_name} (Patient ID: {patient_id}).\n"
            f"Assigned Appointment: {final_appointment_date} at {final_appointment_time}\n"
            f"Referring Doctor: {REFERRING_DOCTOR_NAME}\n" # Using hardcoded referring doctor
            f"Urgency: {'Urgent' if urgent else 'Routine'}\n\n"
            f"--- Patient Symptoms & Treatment Details ---\n{treatment_details}\n\n"
            f"--- Patient History (from record) ---\n{patient_history}\n\n"
            f"Please review and contact the patient as appropriate regarding this appointment.\n\n"
            f"Sincerely,\nAI Medical Assistant (System for Learning - Do Not Reply)"
        )
        
        specialist_html_body = (
            f"<p><strong>Dear Specialist/Referral Department,</strong></p>"
            f"<p>This is a referral for patient <strong>{final_patient_name}</strong> (Patient ID: {patient_id}).</p>"
            f"<p><strong>Assigned Appointment:</strong> {final_appointment_date} at {final_appointment_time}</p>"
            f"<p><strong>Referring Doctor:</strong> {REFERRING_DOCTOR_NAME}</p>" # Using hardcoded referring doctor
            f"<p><strong>Urgency:</strong> {'<span style=\"color: red; font-weight: bold;\">URGENT</span>' if urgent else 'Routine'}</p>"
            f"<p><strong>Patient Symptoms & Treatment Details:</strong><br>{treatment_details.replace('\n', '<br>')}</p>"
            f"<p><strong>Patient History (from record):</strong><br>{patient_history.replace('\n', '<br>')}</p>"
            f"<p>Please review and contact the patient as appropriate regarding this appointment.</p>"
            f"<p>Sincerely,<br>AI Medical Assistant (System for Learning - Do Not Reply)</p>"
        )

        # --- Construct Patient Email Content ---
        patient_subject = f"Your Specialist Appointment Confirmation: {appointment_id}"
        patient_plain_text_body = (
            f"Dear {final_patient_name},\n\n"
            f"Your specialist appointment has been booked.\n"
            f"Appointment ID: {appointment_id}\n"
            f"Date: {final_appointment_date}\n"
            f"Time: {final_appointment_time}\n"
            f"Referring Doctor: {REFERRING_DOCTOR_NAME}\n" # Using hardcoded referring doctor
            f"Reason for visit: {symptoms}\n\n"
            f"Further details will be provided by the specialist's office.\n\n"
            f"Please remember: This is a confirmation for learning purposes only. "
            f"Always consult a real healthcare professional for actual medical needs."
        )
        patient_html_body = (
            f"<p><strong>Dear {final_patient_name},</strong></p>"
            f"<p>Your specialist appointment has been booked.</p>"
            f"<p><strong>Appointment ID:</strong> {appointment_id}</p>"
            f"<p><strong>Date:</strong> {final_appointment_date}</p>"
            f"<p><strong>Time:</strong> {final_appointment_time}</p>"
            f"<p><strong>Referring Doctor:</strong> {REFERRING_DOCTOR_NAME}</p>" # Using hardcoded referring doctor
            f"<p><strong>Reason for visit:</strong> {symptoms}</p>"
            f"<p>Further details will be provided by the specialist's office.</p>"
            f"<p>Please remember: This is a confirmation for learning purposes only. "
            f"Always consult a real healthcare professional for actual medical needs.</p>"
        )

        # --- Attempt to send emails ---
        specialist_email_sent_status, specialist_email_message = send_email_via_smtp(
            to_email=SPECIALIST_EMAIL, # Using hardcoded specialist email
            subject=specialist_subject,
            plain_text_content=specialist_plain_text_body,
            html_content=specialist_html_body
        )

        patient_email_sent_status = False
        patient_email_message = "Patient email not provided or invalid."
        if final_patient_email and re.match(email_regex, final_patient_email):
            patient_email_sent_status, patient_email_message = send_email_via_smtp(
                to_email=final_patient_email,
                subject=patient_subject,
                plain_text_content=patient_plain_text_body,
                html_content=patient_html_body
            )
        else:
            patient_email_message = "Patient email not found in database or invalid format."
        
        # --- Store appointment details in Firestore ---
        appointment_details_to_store = {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "appointment_type": appointment_type,
            "assigned_date": final_appointment_date,
            "assigned_time": final_appointment_time,
            "symptoms": symptoms,
            "duration_value": duration_value,
            "duration_unit": duration_unit,
            "patient_name": final_patient_name,
            "specialist_email": SPECIALIST_EMAIL, # Store hardcoded specialist email
            "patient_email": final_patient_email,
            "referring_doctor": REFERRING_DOCTOR_NAME, # Store hardcoded referring doctor
            "treatment_details": treatment_details,
            "urgent": urgent,
            "specialist_email_sent_status": specialist_email_sent_status,
            "patient_email_sent_status": patient_email_sent_status,
            "patient_history_retrieved": history_retrieved_success,
            "patient_history_summary": patient_history
        }
        db_save_success, db_save_message = save_appointment_to_firestore(appointment_details_to_store, "specialist_appointments")
        if not db_save_success:
            print(f"Warning: Failed to save specialist appointment to database: {db_save_message}")

        # --- Prepare the JSON response for the AI Agent ---
        response_message = "Specialist appointment booked and emails sent."
        if not specialist_email_sent_status:
            response_message += f" Issue sending specialist email: {specialist_email_message}."
        if not patient_email_sent_status: # Changed condition
            response_message += f" Issue sending patient email: {patient_email_message}."
        if not db_save_success:
            response_message += f" (Note: Failed to save appointment to database: {db_save_message})"

        response_data = {
            "success": specialist_email_sent_status and patient_email_sent_status and db_save_success,
            "message": response_message,
            "assigned_date": final_appointment_date,
            "assigned_time": final_appointment_time,
            "appointment_id": appointment_id,
            "patient_email_sent_status": patient_email_sent_status,
            "specialist_email_sent_status": specialist_email_sent_status,
            "db_save_success": db_save_success,
            "confirmation_email_address": final_patient_email # Add final patient email to response
        }
        return jsonify(response_data), 200

    except Exception as e:
        print(f"Error in specialist referral email backend: {e}")
        return jsonify({"success": False, "message": f"Internal server error: {str(e)}"}), 500

# Standard boilerplate for running a Flask application.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
