"""
generation_tasks.py

Two jobs that run before each dispatch window:

  prepare_all_tips()
      Enqueues AI processing for every currently active subscriber.
      Marks each msisdn in a Redis window-set so we know who was handled.
      Messages are separated into {"last_24h": [...], "older": [...]} so the
      classifier can apply recency-based topic scoring.

  prepare_late_subscribers()
      Runs just before the send job. Re-queries the subscriber list and
      only processes MSISDNs that are NOT yet in the window-set — these are
      new subscribers who joined after prepare_all_tips ran.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config.logger import logger
from app.config.settings import settings
from app.conversations.aggregator import aggregate_conversations
from app.database.chat_history import fetch_recent_conversations
from app.database.subscriptions import fetch_active_subscribers
from app.queue.redis_client import ai_queue, redis_conn

# Redis key prefix for the per-window prepared-subscriber set
_WINDOW_KEY_PREFIX    = "smart_tips:dispatch_window"
_WINDOW_TTL_SECONDS   = 4 * 60 * 60   # 4 hours — covers the full prepare→dispatch window

# Default empty message structure (sent when subscriber has no chat history)
_EMPTY_MESSAGES: dict = {'last_24h': [], 'older': []}


# ── Window helpers ────────────────────────────────────────────────────────────

def _get_window_key() -> str:
    """Return the Redis key for the current send window.

    Morning window  (sends at 07:00): key = ...YYYYMMDD_0700
    Evening window  (sends at 19:00): key = ...YYYYMMDD_1900
    """
    try:
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = None
    now       = datetime.now(tz) if tz else datetime.now()
    send_hour = 7 if now.hour < 12 else 19
    return f"{_WINDOW_KEY_PREFIX}:{now.strftime('%Y%m%d')}_{send_hour:02d}00"


def _mark_prepared(msisdn: str):
    key = _get_window_key()
    redis_conn.sadd(key, msisdn)
    redis_conn.expire(key, _WINDOW_TTL_SECONDS)


def _is_prepared(msisdn: str) -> bool:
    key = _get_window_key()
    return bool(redis_conn.sismember(key, msisdn))


# ── Jobs ──────────────────────────────────────────────────────────────────────

def prepare_all_tips():
    """Enqueue AI processing for every active subscriber.
    Runs ~50 minutes before the send job so workers have time to finish.
    """
    subscribers = fetch_active_subscribers()
    rows        = fetch_recent_conversations()
    grouped     = aggregate_conversations(rows)

    logger.info(
        'prepare_all_tips_chat_stats',
        extra={
            'event':                'prepare_all_tips_chat_stats',
            'total_subscribers':    len(subscribers),
            'subscribers_with_history': len(grouped),
        }
    )

    enqueued = 0
    for msisdn in subscribers:
        # Mark BEFORE enqueuing so the late-catch job can detect in-progress ones
        _mark_prepared(msisdn)
        messages = grouped.get(msisdn, _EMPTY_MESSAGES)

        try:
            ai_queue.enqueue('app.tasks.ai_tasks.process_profile', msisdn, messages)
            enqueued += 1
        except Exception as exc:
            logger.exception(
                'prepare_enqueue_failed',
                extra={
                    'event':  'prepare_enqueue_failed',
                    'msisdn': msisdn,
                    'error':  str(exc),
                }
            )

    logger.info(
        'prepare_all_tips_done',
        extra={
            'event':             'prepare_all_tips_done',
            'enqueued':          enqueued,
            'total_subscribers': len(subscribers),
        }
    )


def prepare_late_subscribers():
    """Catch subscribers who joined after prepare_all_tips ran.
    Runs ~5 minutes before the send job as a final sweep.
    Only processes MSISDNs not already in the window Redis set.
    """
    subscribers = fetch_active_subscribers()
    rows        = fetch_recent_conversations()
    grouped     = aggregate_conversations(rows)

    late = 0
    for msisdn in subscribers:
        if _is_prepared(msisdn):
            continue  # already handled — skip

        _mark_prepared(msisdn)
        messages = grouped.get(msisdn, _EMPTY_MESSAGES)

        try:
            ai_queue.enqueue('app.tasks.ai_tasks.process_profile', msisdn, messages)
            late += 1
        except Exception as exc:
            logger.exception(
                'late_enqueue_failed',
                extra={
                    'event':  'late_enqueue_failed',
                    'msisdn': msisdn,
                    'error':  str(exc),
                }
            )

    logger.info(
        'late_subscribers_queued',
        extra={
            'event':             'late_subscribers_queued',
            'count':             late,
            'total_subscribers': len(subscribers),
        }
    )
