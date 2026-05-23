from datetime import timedelta
from app.config.logger import logger
from app.queue.redis_client import retry_queue
from app.sms.sender import send_sms

MAX_RETRY_ATTEMPTS = 2
RETRY_DELAY_MINUTES = 5


def retry_send_sms(msisdn, message, attempt=1):
    try:
        result = send_sms(msisdn, message)
        logger.info(
            'sms_send_success',
            extra={
                'event': 'sms_send_success',
                'msisdn': msisdn,
                'port': result.get('port'),
                'status_code': result.get('status')
            }
        )
        return result
    except Exception as exc:
        logger.warning(
            'sms_send_retry',
            extra={
                'event': 'sms_send_retry',
                'msisdn': msisdn,
                'attempt': attempt,
                'error': str(exc)
            }
        )

        if attempt < MAX_RETRY_ATTEMPTS:
            retry_queue.enqueue_in(
                timedelta(minutes=RETRY_DELAY_MINUTES * attempt),
                'app.tasks.retry_tasks.retry_send_sms',
                msisdn,
                message,
                attempt + 1
            )
            return {
                'status': 'scheduled',
                'next_attempt': attempt + 1
            }

        logger.error(
            'sms_send_failed_max_retries',
            extra={
                'event': 'sms_send_failed_max_retries',
                'msisdn': msisdn,
                'attempts': attempt,
                'error': str(exc)
            }
        )
        raise
