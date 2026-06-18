"""
generation_tasks.py

Two jobs that run before each dispatch window:

  prepare_all_tips()
      Separates all active subscribers into two groups:

      No-history  (~97% of subscribers):
          Pool tips are assigned via a single bulk DB INSERT — no queue,
          no per-subscriber overhead.  All ready within seconds.

      With-history (~3% of subscribers):
          One RQ task per subscriber → AI worker classifies + generates a
          personalised tip.  Multiple workers run these in parallel.

      Both groups are marked in the Redis window-set so the late-catch job
      doesn't re-process them.

  prepare_late_subscribers()
      Runs ~5 min before the send job.  Only processes MSISDNs that are
      NOT already in the window Redis set (new subs who joined after
      prepare_all_tips ran).  Same split logic applies.
"""

import hashlib
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config.logger import logger
from app.config.settings import settings
from app.conversations.aggregator import aggregate_conversations
from app.database.chat_history import fetch_recent_conversations
from app.database.generated_tips import bulk_insert_pool_tips
from app.database.subscriptions import fetch_active_subscribers
from app.queue.redis_client import ai_queue, redis_conn
from app.tasks.prefetch_tasks import get_pool_tips

_WINDOW_KEY_PREFIX  = "smart_tips:dispatch_window"
_WINDOW_TTL_SECONDS = 4 * 60 * 60
_EMPTY_MESSAGES: dict = {'last_24h': [], 'older': []}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    norm = unicodedata.normalize('NFC', text).strip().lower()
    norm = re.sub(r'\s+', ' ', norm)
    norm = ''.join(ch for ch in norm if unicodedata.category(ch)[0] != 'P')
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


def _get_window_key() -> str:
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
    return bool(redis_conn.sismember(_get_window_key(), msisdn))


def _bulk_assign_pool_tips(msisdns: list):
    """Bulk-assign Swahili pool tips to no-history subscribers in one DB round-trip."""
    if not msisdns:
        return 0

    pool = get_pool_tips('sw')
    if not pool:
        # Pool unavailable — fall back to individual RQ tasks so these
        # subscribers are not silently dropped.
        logger.warning(
            'pool_empty_fallback_to_queue',
            extra={
                'event': 'pool_empty_fallback_to_queue',
                'count': len(msisdns),
            }
        )
        for msisdn in msisdns:
            try:
                ai_queue.enqueue('app.tasks.ai_tasks.process_profile',
                                 msisdn, _EMPTY_MESSAGES)
            except Exception as exc:
                logger.exception(
                    'prepare_enqueue_failed',
                    extra={'event': 'prepare_enqueue_failed',
                           'msisdn': msisdn, 'error': str(exc)}
                )
        return 0

    records = [
        {
            'msisdn':   msisdn,
            'language': 'sw',
            'tip':      pool[i % len(pool)],
            'tip_hash': _sha256(pool[i % len(pool)]),
        }
        for i, msisdn in enumerate(msisdns)
    ]

    inserted = bulk_insert_pool_tips(records)
    logger.info(
        'bulk_pool_tips_inserted',
        extra={
            'event':    'bulk_pool_tips_inserted',
            'count':    inserted,
            'pool_size': len(pool),
        }
    )
    return inserted


# ── Jobs ──────────────────────────────────────────────────────────────────────

def prepare_all_tips():
    """Enqueue/insert tips for every active subscriber before the dispatch window."""
    subscribers = fetch_active_subscribers()
    rows        = fetch_recent_conversations()
    grouped     = aggregate_conversations(rows)

    no_history:   list = []
    with_history: list = []

    for msisdn in subscribers:
        _mark_prepared(msisdn)
        messages = grouped.get(msisdn, _EMPTY_MESSAGES)
        if messages.get('last_24h') or messages.get('older'):
            with_history.append((msisdn, messages))
        else:
            no_history.append(msisdn)

    logger.info(
        'prepare_all_tips_chat_stats',
        extra={
            'event':                   'prepare_all_tips_chat_stats',
            'total_subscribers':       len(subscribers),
            'subscribers_with_history': len(with_history),
            'subscribers_no_history':  len(no_history),
        }
    )

    # ── Path B: enqueue AI tasks FIRST so workers start immediately ──────────
    # (bulk insert below is slower; doing it last avoids blocking AI workers)
    enqueued = 0
    for msisdn, messages in with_history:
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

    # ── Path A: bulk insert pool tips after AI tasks are queued ─────────────
    _bulk_assign_pool_tips(no_history)

    logger.info(
        'prepare_all_tips_done',
        extra={
            'event':             'prepare_all_tips_done',
            'enqueued_ai':       enqueued,
            'bulk_inserted':     len(no_history),
            'total_subscribers': len(subscribers),
        }
    )


def prepare_late_subscribers():
    """Catch subscribers who joined after prepare_all_tips ran."""
    subscribers = fetch_active_subscribers()
    rows        = fetch_recent_conversations()
    grouped     = aggregate_conversations(rows)

    late_no_history:   list = []
    late_with_history: list = []

    for msisdn in subscribers:
        if _is_prepared(msisdn):
            continue

        _mark_prepared(msisdn)
        messages = grouped.get(msisdn, _EMPTY_MESSAGES)
        if messages.get('last_24h') or messages.get('older'):
            late_with_history.append((msisdn, messages))
        else:
            late_no_history.append(msisdn)

    _bulk_assign_pool_tips(late_no_history)

    late_enqueued = 0
    for msisdn, messages in late_with_history:
        try:
            ai_queue.enqueue('app.tasks.ai_tasks.process_profile', msisdn, messages)
            late_enqueued += 1
        except Exception as exc:
            logger.exception(
                'late_enqueue_failed',
                extra={
                    'event':  'late_enqueue_failed',
                    'msisdn': msisdn,
                    'error':  str(exc),
                }
            )

    late_total = len(late_no_history) + late_enqueued
    logger.info(
        'late_subscribers_queued',
        extra={
            'event':             'late_subscribers_queued',
            'count':             late_total,
            'bulk_inserted':     len(late_no_history),
            'enqueued_ai':       late_enqueued,
            'total_subscribers': len(subscribers),
        }
    )
