"""
dispatch_tasks.py

Two public functions:

  dispatch_all_ready_tips()
      Runs at 07:00 / 19:00. Sends all delivery_status='ready' tips at
      SMS_TPS using round-robin + per-port failover.
      On total failure: marks 'failed', retry_count stays 0.

  retry_failed_tips()
      Runs at 07:15 & 07:30 / 19:15 & 19:30.
      Re-attempts tips with delivery_status='failed' AND retry_count < MAX_RETRIES.
      On success: marks 'sent'.
      On failure: increments retry_count (stays 'failed' for next retry job to pick up).
      After retry_count reaches MAX_RETRIES the tip is abandoned.

Max total send attempts per tip: 1 dispatch + MAX_RETRIES retries = 3.
"""

import time
import requests
from requests.exceptions import RequestException

from app.config.logger import logger
from app.config.settings import settings
from app.database.generated_tips import (
    expire_stale_ready_tips,
    fetch_failed_tips,
    fetch_ready_tips,
    increment_retry_count,
    update_delivery_status,
)
from app.database.sms_logs import insert_sms_log

PORTS = [p.strip() for p in settings.SMS_PORTS.split(',') if p.strip()]
TPS_LIMIT = settings.SMS_TPS
MAX_RETRIES = 2   # tips are retried at most this many times after initial dispatch


# ── Shared helpers ────────────────────────────────────────────────────────────

def _send_on_port(msisdn: str, message: str, port: str) -> requests.Response:
    url = f"http://{settings.SMS_HOST}:{port}/cgi-bin/sendsms"
    payload = {
        "username": settings.SMS_USERNAME,
        "password": settings.SMS_PASSWORD,
        "from": settings.SMS_FROM,
        "to": msisdn,
        "text": message,
    }
    return requests.get(url, params=payload, timeout=20)


def _send_tips(tips, label: str = 'dispatch') -> list:
    """
    Core send loop shared by dispatch and retry.

    Returns a list of result dicts:
        {'tip_id', 'msisdn', 'sms_text', 'success': bool, 'port': str|None}

    Handles:
      - TPS rate limiting (SMS_TPS per second)
      - Round-robin port assignment (port_index advances every subscriber)
      - Per-port failover (tries next port if primary is down)
      - sms_log insertion for every attempt (success and failure)
    """
    if not tips:
        return []

    port_index = 0
    results = []
    window_start = time.time()
    sent_in_window = 0

    for row in tips:
        tip_id   = row[0]
        msisdn   = row[1]
        sms_text = row[3]   # row[2] = language

        # ── Rate limiting ────────────────────────────────────────────────────
        sent_in_window += 1
        if sent_in_window > TPS_LIMIT:
            elapsed = time.time() - window_start
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            sent_in_window = 1
            window_start = time.time()

        # ── Round-robin with failover ────────────────────────────────────────
        # e.g. PORTS=[6016,6017,6018], port_index=1 → try [6017, 6018, 6016]
        ports_to_try = [PORTS[(port_index + i) % len(PORTS)] for i in range(len(PORTS))]
        port_index = (port_index + 1) % len(PORTS)   # always advance

        success = False
        used_port = None

        for port in ports_to_try:
            try:
                response = _send_on_port(msisdn, sms_text, port)
                insert_sms_log(
                    msisdn=msisdn,
                    message_text=sms_text,
                    status='sent',
                    port=port,
                    response_code=response.status_code,
                )
                logger.info(
                    f'{label}_sms_sent',
                    extra={
                        'event': f'{label}_sms_sent',
                        'msisdn': msisdn,
                        'port': port,
                        'status_code': response.status_code,
                    }
                )
                success = True
                used_port = port
                break

            except RequestException as exc:
                insert_sms_log(
                    msisdn=msisdn,
                    message_text=sms_text,
                    status='port_unavailable',
                    port=port,
                    error=str(exc),
                )
                logger.warning(
                    f'{label}_port_unavailable',
                    extra={
                        'event': f'{label}_port_unavailable',
                        'msisdn': msisdn,
                        'port': port,
                        'error': str(exc),
                    }
                )

        if not success:
            insert_sms_log(
                msisdn=msisdn,
                message_text=sms_text,
                status='failed',
                error='all_ports_unavailable',
            )
            logger.error(
                f'{label}_all_ports_failed',
                extra={'event': f'{label}_all_ports_failed', 'msisdn': msisdn}
            )

        results.append({
            'tip_id':   tip_id,
            'msisdn':   msisdn,
            'sms_text': sms_text,
            'success':  success,
            'port':     used_port,
        })

    return results


# ── Public jobs ───────────────────────────────────────────────────────────────

def dispatch_all_ready_tips():
    """Initial dispatch at 07:00 / 19:00. Sends all 'ready' tips."""
    # Expire tips from previous missed windows before reading ready count.
    # This cleans up stale 'ready' rows that accumulated when the bulk insert
    # ran late (e.g. after dispatch already fired) and prevents them from
    # clogging the table forever.
    expired = expire_stale_ready_tips(older_than_hours=6)
    if expired:
        logger.info(
            'stale_tips_expired',
            extra={'event': 'stale_tips_expired', 'count': expired}
        )

    tips = fetch_ready_tips()

    if not tips:
        logger.info('dispatch_no_ready_tips', extra={'event': 'dispatch_no_ready_tips'})
        return

    logger.info(
        'dispatch_started',
        extra={'event': 'dispatch_started', 'total': len(tips), 'ports': PORTS, 'tps': TPS_LIMIT}
    )

    results = _send_tips(tips, label='dispatch')

    sent = failed = 0
    for r in results:
        if r['success']:
            update_delivery_status(r['tip_id'], 'sent')
            sent += 1
        else:
            update_delivery_status(r['tip_id'], 'failed')  # retry_count stays 0
            failed += 1

    logger.info(
        'dispatch_complete',
        extra={'event': 'dispatch_complete', 'sent': sent, 'failed': failed, 'total': len(tips)}
    )


def retry_failed_tips():
    """
    Retry tips that failed in the current window.
    Runs at +15 min and +30 min after dispatch.

    Success  → delivery_status = 'sent'
    Failure  → retry_count += 1  (stays 'failed'; next retry job picks it up
                                   until retry_count reaches MAX_RETRIES)
    """
    tips = fetch_failed_tips(max_retries=MAX_RETRIES, window_hours=2)

    if not tips:
        logger.info('retry_no_failed_tips', extra={'event': 'retry_no_failed_tips'})
        return

    logger.info(
        'retry_started',
        extra={'event': 'retry_started', 'total': len(tips)}
    )

    results = _send_tips(tips, label='retry')

    sent = failed = 0
    for r in results:
        if r['success']:
            update_delivery_status(r['tip_id'], 'sent')
            sent += 1
        else:
            increment_retry_count(r['tip_id'])   # bump counter, keep 'failed'
            failed += 1

    logger.info(
        'retry_complete',
        extra={
            'event': 'retry_complete',
            'sent': sent,
            'exhausted': sum(1 for r in results if not r['success']),
            'total': len(tips),
        }
    )
