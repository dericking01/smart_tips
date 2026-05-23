import time
import requests
from requests.exceptions import RequestException
from app.config.logger import logger
from app.config.settings import settings
from app.database.sms_logs import insert_sms_log
from app.queue.redis_client import redis_conn

PORTS = [port.strip() for port in settings.SMS_PORTS.split(',') if port.strip()]
TPS = int(getattr(settings, 'SMS_TPS', 200))


def _wait_for_slot():
    # Redis-based per-second counter to enforce overall TPS across workers
    now = int(time.time())
    key = f"sms_rate:global:{now}"
    count = redis_conn.incr(key)
    if count == 1:
        # expire after 2 seconds to cover clock skew
        redis_conn.expire(key, 2)

    if count <= TPS:
        return

    # rate exceeded; sleep until next second boundary then try again
    wait = 1.0 - (time.time() - now)
    if wait < 0:
        wait = 0.01
    time.sleep(wait)


def send_sms(msisdn, message):
    last_error = None
    attempt = 0

    for port in PORTS:
        attempt += 1

        # enforce overall TPS using Redis
        _wait_for_slot()

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