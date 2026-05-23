import requests
from app.sms.round_robin import get_next_port
from app.config.settings import settings

def send_sms(msisdn, message):
    port = get_next_port()

    url = f"http://{settings.SMS_HOST}:{port}/cgi-bin/sendsms"

    payload = {
        "username": settings.SMS_USERNAME,
        "password": settings.SMS_PASSWORD,
        "from": settings.SMS_FROM,
        "to": msisdn,
        "text": message
    }

    response = requests.get(url, params=payload, timeout=20)

    return {
        "status": response.status_code,
        "response": response.text,
        "port": port
    }