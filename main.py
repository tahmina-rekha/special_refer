# main.py (for refer_special Cloud Run service)
import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# This route matches the '/send_referral_email' path in your refer_special OpenAPI YAML
@app.route('/send_referral_email', methods=['POST'])
def send_referral_email_backend():
    """
    Handles incoming POST requests to simulate sending a specialist referral email.
    
    This function processes referral details from the agent and returns a dummy
    success response, simulating an email being sent.
    
    Args:
        request (flask.Request): The incoming request object containing referral details.
                                 Expected JSON body includes:
                                 - recipient_email (str)
                                 - patient_name (str)
                                 - referring_doctor (str)
                                 - treatment_details (str)
                                 - patient_id (str, optional)
                                 - urgent (bool, optional)
                                 
    Returns:
        flask.Response: A JSON response confirming simulated email sending,
                        with a 200 OK status code and application/json header.
    """
    
    try:
        request_data = request.get_json()
        
        # Extract data (for a real app, you'd use these to send an actual email)
        recipient_email = request_data.get('recipient_email')
        patient_name = request_data.get('patient_name')
        referring_doctor = request_data.get('referring_doctor')
        treatment_details = request_data.get('treatment_details')
        patient_id = request_data.get('patient_id')
        urgent = request_data.get('urgent', False)

        print(f"Simulating email to: {recipient_email}")
        print(f"Patient: {patient_name} (ID: {patient_id or 'N/A'})")
        print(f"From: {referring_doctor}")
        print(f"Urgent: {urgent}")
        print(f"Treatment Details: {treatment_details[:100]}...") # Print first 100 chars

        # In a real application, you would integrate with an email sending service here
        # (e.g., SendGrid, Mailgun, or Google Cloud Sendgrid integration).

        dummy_response_data = {
            "success": True,
            "message": f"Simulated referral email for {patient_name} to {recipient_email} sent successfully.",
            "email_status": "simulated_sent",
            "mock_email_id": "mock_email_" + os.urandom(8).hex() # A dummy ID
        }
        return jsonify(dummy_response_data), 200

    except Exception as e:
        print(f"Error processing referral request: {e}")
        return jsonify({"success": False, "error": f"Failed to process request: {str(e)}"}), 500

# Standard boilerplate for running a Flask application.
# Cloud Run automatically sets the 'PORT' environment variable.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)