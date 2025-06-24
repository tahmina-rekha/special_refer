# main.py (for your 'special-referral-email' Cloud Run service)
import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS # Import CORS
# Import SMTP libraries
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app) # Enable CORS for your Flask app

# --- SMTP Credentials (ENSURE THESE ARE SET AS ENVIRONMENT VARIABLES IN CLOUD RUN) ---
# These variables should be configured in your Cloud Run service settings, NOT hardcoded here.
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587)) # Default to 587 (TLS/STARTTLS)
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'niljoshna28@gmail.com') # Must be a verified sender email

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
        # Create the email message in multipart format (for both plain text and HTML)
        msg = MIMEMultipart("alternative")
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach plain text and HTML versions
        part1 = MIMEText(plain_text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)

        # Connect to the SMTP server and send the email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            # Start TLS encryption for security (standard for port 587)
            server.starttls()
            # Log in to the SMTP server with credentials
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            # Send the email
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

# --- Main route for the specialist referral email tool ---
# This endpoint corresponds to the '/send_referral_email' path in your OpenAPI YAML
@app.route('/send_referral_email', methods=['POST'])
def send_referral_email_backend():
    """
    Handles incoming POST requests from the AI agent to send a specialist referral email.
    Extracts referral details, constructs an email, and attempts to send it via SMTP.
    Returns a JSON response indicating success or failure of the email sending.
    """
    try:
        request_data = request.get_json()
        
        # Extract all parameters from the request body as defined in OpenAPI
        recipient_email = request_data.get('recipient_email')
        patient_name = request_data.get('patient_name')
        patient_id = request_data.get('patient_id', 'N/A') # Optional, default if not provided
        referring_doctor = request_data.get('referring_doctor')
        treatment_details = request_data.get('treatment_details')
        urgent = request_data.get('urgent', False) # Optional, default to False

        # --- Input Validation ---
        # Basic checks for required fields and email format
        if not all([recipient_email, patient_name, referring_doctor, treatment_details]):
            return jsonify({"success": False, "message": "Missing one or more required referral details (recipient_email, patient_name, referring_doctor, treatment_details)."}), 400
        if '@' not in recipient_email or '.' not in recipient_email:
            return jsonify({"success": False, "message": "Invalid recipient email format provided."}), 400

        # --- Logging incoming request for debugging ---
        print(f"Received referral request:")
        print(f"  Recipient: {recipient_email}")
        print(f"  Patient: {patient_name} (ID: {patient_id})")
        print(f"  Referring Doctor: {referring_doctor}")
        print(f"  Urgent: {urgent}")
        print(f"  Treatment Details (first 100 chars): {treatment_details[:100]}...")

        # --- Construct Email Content ---
        urgency_prefix = "URGENT: " if urgent else ""
        email_subject = f"{urgency_prefix}Specialist Referral for {patient_name} (ID: {patient_id})"
        
        plain_text_body = (
            f"Dear Specialist/Referral Department,\n\n"
            f"This is a referral for patient {patient_name} (Patient ID: {patient_id}).\n"
            f"Referring Doctor: {referring_doctor}\n"
            f"Urgency: {'Urgent' if urgent else 'Routine'}\n\n"
            f"--- Treatment Details ---\n{treatment_details}\n\n"
            f"Please review and contact the patient as appropriate.\n\n"
            f"Sincerely,\nAI Medical Assistant (Simulated System - Do Not Reply)"
        )
        
        html_body = (
            f"<p><strong>Dear Specialist/Referral Department,</strong></p>"
            f"<p>This is a referral for patient <strong>{patient_name}</strong> (Patient ID: {patient_id}).</p>"
            f"<p><strong>Referring Doctor:</strong> {referring_doctor}</p>"
            f"<p><strong>Urgency:</strong> {'<span style=\"color: red; font-weight: bold;\">URGENT</span>' if urgent else 'Routine'}</p>"
            f"<p><strong>Treatment Details:</strong><br>{treatment_details.replace('\n', '<br>')}</p>"
            f"<p>Please review and contact the patient as appropriate.</p>"
            f"<p>Sincerely,<br>AI Medical Assistant (Simulated System - Do Not Reply)</p>"
        )

        # --- Attempt to send the email ---
        email_success, email_message = send_email_via_smtp(
            to_email=recipient_email,
            subject=email_subject,
            plain_text_content=plain_text_body,
            html_content=html_body
        )

        response_data = {
            "success": email_success,
            "message": email_message
        }
        return jsonify(response_data), 200 # Always return 200, success field indicates email status

    except Exception as e:
        print(f"Error in specialist referral email backend: {e}")
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500

# Standard boilerplate for running a Flask application.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
