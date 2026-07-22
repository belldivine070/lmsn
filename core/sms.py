import requests
from django.conf import settings
from core.models import AppVariable



def validate_and_format_international(phone_string):
    """
    STAGE 1: Queries APILayer to verify if an international number is real 
    and transforms it into a clean, normalized E.164 string format.
    """
    clean_number = str(phone_string).strip().replace('+', '%2B')
    url = f"https://api.apilayer.com/number_verification/validate?number={clean_number}"

    smsapi = AppVariable.get_setting('APP_SMSAPI')
    
    headers = { "apikey": smsapi }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('valid') is True:
                return {
                    'valid': True,
                    'international_format': data.get('international_format'), # e.g. "+234 704 713 7084"
                    'country_name': data.get('country_name')                  # e.g. "Nigeria"
                }
    except Exception as e:
        print(f"[APILAYER ERROR] Validation check failed: {e}")
        
    return {'valid': False, 'international_format': None, 'country_name': None}


def send_sms_otp(phone_number, otp_code):
    """
    STAGE 2: Routes the message through the native BulkSMSLive REST API.
    """
    # 1. Inspect number structural format parameters via APILayer
    lookup = validate_and_format_international(phone_number)
    if not lookup['valid'] or not lookup['international_format']:
        return False, "The phone number structural format is globally invalid."

    # BulkSMSLive expects clean continuous numeric sequences (e.g., "2347047137084")
    clean_destination = lookup['international_format'].replace("+", "").replace(" ", "")

    sms_email = AppVariable.get_setting('APP_SMSEMAIL')
    sms_password = AppVariable.get_setting('APP_SMSPWD')
    sms_sender = AppVariable.get_setting('APP_SMSNAME')
    
    # 2. Build the BulkSMSLive payload structure
    url = "https://api.bulksmslive.com/v2/app/sms"
    payload = {
        "email": sms_email,
        "password": sms_password,
        "sender_name": sms_sender,
        "recipients": clean_destination,
        "message": f"Your BGTECH verification code is: {otp_code}. Valid for 10 minutes.",
        "forcednd": "1"  # Instructs BulkSMSLive routes to override carrier DND active locks
    }

    # 3. Fire payload out live
    try:
        response = requests.post(url, json=payload, timeout=12)
        
        # Check if response status is 200 OK
        if response.status_code == 200:
            # BulkSMSLive returns raw text or JSON like {"status": "Ok"} or just a string response
            response_text = response.text.strip()
            
            if "Ok" in response_text or '"status":"Ok"' in response_text.replace(" ", ""):
                print(f"[BULKSMSLIVE SUCCESS] Token delivered successfully to {clean_destination}")
                return True, f"A security code has been texted to {lookup['international_format']} ({lookup['country_name']})."
            else:
                print(f"\n[BULKSMSLIVE API REJECTION] Server Response: {response_text}\n")
                return False, f"SMS Gateway Rejection: {response_text}"
        else:
            print(f"\n[BULKSMSLIVE CRITICAL ERROR] HTTP Status: {response.status_code} - {response.text}\n")
            return False, "SMS delivery engine returned a connection error."

    except Exception as e:
        print(f"\n[DEV FALLBACK] Network delivery exception! Real OTP code token is: {otp_code}. Error: {e}\n")
        return False, "SMS carrier delivery subsystem offline. Please try email validation instead."


def validate_email_deliverability(email_string):
    """
    Queries APILayer's Email Verification API to check for syntax correctness,
    domain MX records, disposable email detection, and actual mailbox existence.
    """
    apiLayer_Email = AppVariable.get_setting('API_1')
    apiLayer_key = AppVariable.get_setting('API_2')
    target_email = email_string.strip().lower()
    url = f"{apiLayer_Email}{target_email}"
    
    headers = { "apikey": apiLayer_key }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            is_valid_format = data.get('format_valid', data.get('syntax_valid', False))
            is_deliverable = data.get('is_deliverable', data.get('smtp_check', False))
            disposable = data.get('disposable', data.get('is_disposable', False))
            
            if disposable:
                return False, "Temporary/disposable email addresses are restricted."
                
            if is_valid_format and is_deliverable:
                return True, "Email verified."
                
            suggestion = data.get('did_you_mean')
            if suggestion:
                return False, f"Email undeliverable. Did you mean {suggestion}?"
                
            return False, "This email address does not seem to exist or cannot receive mail right now."
            
    except Exception as e:
        print(f"[APILAYER EMAIL ERROR] Connection failed: {e}")
        return True, "Validation skipped due to server timeout."

    return False, "Invalid email address."