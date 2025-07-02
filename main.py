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
# This block runs at global scope during module import.
if not firebase_admin._apps:
    try:
        # Use Application Default Credentials (ADC) provided by Cloud Run environment
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully using Application Default Credentials.")
        # Specify the database ID when getting the Firestore client using 'database_id'
        db = firestore.client(database_id="book-appointment") # Use your named Firestore database
        print("Firestore client initialized for database 'book-appointment'.")
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize Firebase Admin SDK or Firestore client at startup: {e}")
        raise # Re-raise to ensure Cloud Run sees the crash and reports it properly.
else:
    try:
        db = firestore.client(database_id="book-appointment")
        print("Firebase app already initialized, Firestore client obtained.")
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

# --- Helper function to retrieve patient history from Firestore ---
def get_patient_history_from_firestore(patient_id):
    """
    Retrieves a patient's medical history from Firestore.
    Collection path: /artifacts/{appId}/public/data/patient_history
    """
    if db is None:
        return "Firestore client not initialized. Cannot retrieve history.", False

    try:
        collection_path = f"artifacts/{app_id}/public/data/patient_history"
        doc_ref = db.collection(collection_path).document(patient_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            history_details = data.get('history_details', 'No detailed history available.')
            return history_details, True
        else:
            return "No medical history found for this patient ID.", False
    except Exception as e:
        print(f"Error retrieving patient history from Firestore: {e}")
        return f"Error retrieving patient history: {str(e)}", False

# --- Helper function to safely extract string values from potentially nested dictionaries ---
def get_string_param(data_dict, key, default_value=None):
    value = data_dict.get(key)
    if isinstance(value, dict) and value:
        return list(value.values())[0] if value else default_value
    return value if value is not None else default_value

# --- Main route for the specialist referral email tool ---
# This endpoint corresponds to the '/send_referral_email' path in your OpenAPI YAML
@app.route('/send_referral_email', methods=['POST'])
def send_referral_email_backend():
    """
    Handles incoming POST requests from the AI agent to book a specialist appointment,
    send confirmation emails to both patient and specialist, and store details to Firestore.
    This function corresponds to the 'refer_specialist' operationId in the OpenAPI spec.
    """
    try:
        request_data = request.get_json()
        
        # Extract all parameters from the request body as defined in OpenAPI
        recipient_email = get_string_param(request_data, 'recipient_email') # Specialist's email
        patient_email = get_string_param(request_data, 'patient_email') # Patient's email
        patient_name = get_string_param(request_data, 'patient_name')
        patient_id = get_string_param(request_data, 'patient_id', 'N/A')
        referring_doctor = get_string_param(request_data, 'referring_doctor')
        treatment_details = get_string_param(request_data, 'treatment_details')
        urgent = request_data.get('urgent', False)

        symptoms = get_string_param(request_data, 'symptoms', 'unspecified symptoms')
        duration_value = request_data.get('duration_value')
        duration_unit = get_string_param(data_dict=request_data, key='duration_unit') # Explicitly pass data_dict

        # --- Input Validation ---
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        
        if not all([recipient_email, patient_name, referring_doctor, treatment_details]):
            return jsonify({"success": False, "message": "Missing one or more required referral details (recipient_email, patient_name, referring_doctor, treatment_details)."}), 400
        
        if not isinstance(recipient_email, str) or not re.match(email_regex, recipient_email):
            return jsonify({"success": False, "message": "Invalid recipient email format provided."}), 400
        
        # Validate patient email only if provided
        if patient_email and (not isinstance(patient_email, str) or not re.match(email_regex, patient_email)):
            return jsonify({"success": False, "message": "Invalid patient email format provided."}), 400

        # --- Assign Specialist Appointment Date/Time (similar to GP booking logic) ---
        assigned_date = None
        assigned_time = "09:00"
        appointment_type = "Specialist" # Fixed for this tool

        now = datetime.now()
        if duration_value is not None and duration_unit:
            if duration_unit == 'days' and duration_value <= 7:
                assigned_date = now + timedelta(weeks=2) # Specialist usually further out
                assigned_time = "10:00"
            elif duration_unit == 'weeks' and duration_value <= 4: # Up to 4 weeks
                assigned_date = now + timedelta(weeks=3)
                assigned_time = "14:00"
            elif (duration_unit == 'months' and duration_value >= 1) or (duration_unit == 'weeks' and duration_value > 4):
                assigned_date = now + timedelta(weeks=6) # Even further out for chronic/long-term
                assigned_time = "11:00"
            else:
                assigned_date = now + timedelta(weeks=3) # Default for specialist
                assigned_time = "09:30"
        else:
            assigned_date = now + timedelta(weeks=3) # Default if no duration provided
            assigned_time = "09:00"
        
        final_appointment_date = assigned_date.strftime('%Y-%m-%d')
        final_appointment_time = assigned_time

        # --- Generate Appointment ID ---
        appointment_id = f"SPEC-{patient_id.replace('N/A', 'UNKNOWN')[:5]}-{os.urandom(3).hex()}"

        # --- Retrieve Patient History (Conceptual/Simulated) ---
        patient_history, history_retrieved_success = get_patient_history_from_firestore(patient_id)
        if not history_retrieved_success:
            print(f"Warning: Could not retrieve patient history for {patient_id}: {patient_history}")
            patient_history = "No detailed history found or could be retrieved."
        
        # --- Construct Specialist Email Content ---
        urgency_prefix = "URGENT: " if urgent else ""
        specialist_subject = f"{urgency_prefix}Specialist Referral for {patient_name} (Patient ID: {patient_id})"
        
        specialist_plain_text_body = (
            f"Dear Specialist/Referral Department,\n\n"
            f"This is a referral for patient {patient_name} (Patient ID: {patient_id}).\n"
            f"Assigned Appointment: {final_appointment_date} at {final_appointment_time}\n"
            f"Referring Doctor: {referring_doctor}\n"
            f"Urgency: {'Urgent' if urgent else 'Routine'}\n\n"
            f"--- Patient Symptoms & Treatment Details ---\n{treatment_details}\n\n"
            f"--- Patient History (from record) ---\n{patient_history}\n\n"
            f"Please review and contact the patient as appropriate regarding this appointment.\n\n"
            f"Sincerely,\nAI Medical Assistant (System for Learning - Do Not Reply)"
        )
        
        specialist_html_body = (
            f"<p><strong>Dear Specialist/Referral Department,</strong></p>"
            f"<p>This is a referral for patient <strong>{patient_name}</strong> (Patient ID: {patient_id}).</p>"
            f"<p><strong>Assigned Appointment:</strong> {final_appointment_date} at {final_appointment_time}</p>"
            f"<p><strong>Referring Doctor:</strong> {referring_doctor}</p>"
            f"<p><strong>Urgency:</strong> {'<span style=\"color: red; font-weight: bold;\">URGENT</span>' if urgent else 'Routine'}</p>"
            f"<p><strong>Patient Symptoms & Treatment Details:</strong><br>{treatment_details.replace('\n', '<br>')}</p>"
            f"<p><strong>Patient History (from record):</strong><br>{patient_history.replace('\n', '<br>')}</p>"
            f"<p>Please review and contact the patient as appropriate regarding this appointment.</p>"
            f"<p>Sincerely,<br>AI Medical Assistant (System for Learning - Do Not Reply)</p>"
        )

        # --- Construct Patient Email Content ---
        patient_subject = f"Your Specialist Appointment Confirmation: {appointment_id}"
        patient_plain_text_body = (
            f"Dear {patient_name},\n\n"
            f"Your specialist appointment has been booked.\n"
            f"Appointment ID: {appointment_id}\n"
            f"Date: {final_appointment_date}\n"
            f"Time: {final_appointment_time}\n"
            f"Referring Doctor: {referring_doctor}\n"
            f"Reason for visit: {symptoms}\n\n"
            f"Further details will be provided by the specialist's office.\n\n"
            f"Please remember: This is a confirmation for learning purposes only. "
            f"Always consult a real healthcare professional for actual medical needs."
        )
        patient_html_body = (
            f"<p><strong>Dear {patient_name},</strong></p>"
            f"<p>Your specialist appointment has been booked.</p>"
            f"<p><strong>Appointment ID:</strong> {appointment_id}</p>"
            f"<p><strong>Date:</strong> {final_appointment_date}</p>"
            f"<p><strong>Time:</strong> {final_appointment_time}</p>"
            f"<p><strong>Referring Doctor:</strong> {referring_doctor}</p>"
            f"<p><strong>Reason for visit:</strong> {symptoms}</p>"
            f"<p>Further details will be provided by the specialist's office.</p>"
            f"<p>Please remember: This is a confirmation for learning purposes only. "
            f"Always consult a real healthcare professional for actual medical needs.</p>"
        )

        # --- Attempt to send emails ---
        specialist_email_sent_status, specialist_email_message = send_email_via_smtp(
            to_email=recipient_email,
            subject=specialist_subject,
            plain_text_content=specialist_plain_text_body,
            html_content=specialist_html_body
        )

        patient_email_sent_status = False
        patient_email_message = "Patient email not provided or invalid."
        if patient_email and re.match(email_regex, patient_email):
            patient_email_sent_status, patient_email_message = send_email_via_smtp(
                to_email=patient_email,
                subject=patient_subject,
                plain_text_content=patient_plain_text_body,
                html_content=patient_html_body
            )
        
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
            "patient_name": patient_name,
            "specialist_email": recipient_email,
            "patient_email": patient_email,
            "referring_doctor": referring_doctor,
            "treatment_details": treatment_details,
            "urgent": urgent,
            "specialist_email_sent_status": specialist_email_sent_status,
            "patient_email_sent_status": patient_email_sent_status,
            "patient_history_retrieved": history_retrieved_success,
            "patient_history_summary": patient_history # Store the retrieved history
        }
        db_save_success, db_save_message = save_appointment_to_firestore(appointment_details_to_store, "specialist_appointments")
        if not db_save_success:
            print(f"Warning: Failed to save specialist appointment to database: {db_save_message}")

        # --- Prepare the JSON response for the AI Agent ---
        response_message = "Specialist appointment booked and emails sent."
        if not specialist_email_sent_status:
            response_message += f" Issue sending specialist email: {specialist_email_message}."
        if patient_email and not patient_email_sent_status:
            response_message += f" Issue sending patient email: {patient_email_message}."
        if not db_save_success:
            response_message += f" Issue saving to database: {db_save_message}."

        response_data = {
            "success": specialist_email_sent_status and patient_email_sent_status and db_save_success, # Overall success
            "message": response_message,
            "assigned_date": final_appointment_date,
            "assigned_time": final_appointment_time,
            "appointment_id": appointment_id,
            "patient_email_sent_status": patient_email_sent_status,
            "specialist_email_sent_status": specialist_email_sent_status,
            "db_save_success": db_save_success
        }
        return jsonify(response_data), 200

    except Exception as e:
        print(f"Error in specialist referral email backend: {e}")
        return jsonify({"success": False, "message": f"Internal server error: {str(e)}"}), 500

# Standard boilerplate for running a Flask application.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
