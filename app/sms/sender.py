import requests
from requests.exceptions import RequestException
from app.config.logger import logger
from app.config.settings import settings
from app.database.sms_logs import insert_sms_log

PORTS = [port.strip() for port in settings.SMS_PORTS.split(',') if port.strip()]

def send_sms(msisdn, message):
    last_error = None
    attempt = 0

    for port in PORTS:
        attempt += 1
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
            insert_sms_log(
                msisdn=msisdn,
                text=message,
                status='attempt',
                port=port,
                response_code=response.status_code,
                error=None,
                attempt=attempt
            )
            logger.info(
                'sms_send_attempt',
                extra={
                    'event': 'sms_send_attempt',
                    'msisdn': msisdn,
                    'port': port,
                    'status_code': response.status_code,
                    'attempt': attempt
                }
            )
            return {
                "status": response.status_code,
                "response": response.text,
                "port": port
            }
        except RequestException as exc:
            last_error = exc
            insert_sms_log(
                msisdn=msisdn,
                text=message,
                status='port_unavailable',
                port=port,
                response_code=None,
                error=str(exc),
                attempt=attempt
            )
            logger.warning(
                'sms_port_unavailable',
                extra={
                    'event': 'sms_port_unavailable',
                    'msisdn': msisdn,
                    'port': port,
                    'attempt': attempt,
                    'error': str(exc)
                }
            )
            continue

    insert_sms_log(
        msisdn=msisdn,
        text=message,
        status='failed',
        port=None,
        response_code=None,
        error=str(last_error) if last_error else 'all_ports_down',
        attempt=attempt
    )
    logger.error(
        'sms_send_failed',
        extra={
            'event': 'sms_send_failed',
            'msisdn': msisdn,
            'attempt': attempt,
            'error': str(last_error)
        }
    )

    raise last_error or Exception('SMS send failed: all configured SMS ports are unavailable.')