import requests
from requests.exceptions import RequestException
from app.config.logger import logger
from app.config.settings import settings

PORTS = [port.strip() for port in settings.SMS_PORTS.split(',') if port.strip()]

def send_sms(msisdn, message):
    last_error = None

    for port in PORTS:
        url = f"http://{settings.SMS_HOST}:{port}/cgi-bin/sendsms"
        payload = {
            "username": settings.SMS_USERNAME,
            "password": settings.SMS_PASSWORD,
            "from": settings.SMS_FROM,
            "to": msisdn,
            "text": message
        }

        try:
            response = requests.get(url, params=payload, timeout=20)
            logger.info(
                'sms_send_attempt',
                extra={
                    'event': 'sms_send_attempt',
                    'msisdn': msisdn,
                    'port': port,
                    'status_code': response.status_code
                }
            )
            return {
                "status": response.status_code,
                "response": response.text,
                "port": port
            }
        except RequestException as exc:
            last_error = exc
            logger.warning(
                'sms_port_unavailable',
                extra={
                    'event': 'sms_port_unavailable',
                    'msisdn': msisdn,
                    'port': port,
                    'error': str(exc)
                }
            )
            continue

    logger.error(
        'sms_send_failed',
        extra={
            'event': 'sms_send_failed',
            'msisdn': msisdn,
            'error': str(last_error)
        }
    )

    raise last_error or Exception('SMS send failed: all configured SMS ports are unavailable.')