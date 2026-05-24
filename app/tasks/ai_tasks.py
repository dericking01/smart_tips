"""
ai_tasks.py

process_profile(msisdn, messages_by_period)
    Called by the AI worker for every active subscriber.

    messages_by_period = {
        "last_24h": ["human message", ...],   # today's chat messages
        "older":    ["human message", ...],   # 24-48 h ago chat messages
    }

    Path A — no chat history:
        Assign a random tip from the pre-generated Redis pool.
        No OpenAI call; topics stored as [].

    Path B — has chat history:
        1. Classify topics (recency-scored: last_24h > older).
        2. Log classification to smart_tips.classification_logs.
        3. Upsert discovered topics into smart_tips.topics.
        4. Generate a personalised tip focused on the top-scored topic.
        5. Fallback to pool if generation or validation fails.
        6. Store as delivery_status='ready' for the dispatch job.
"""

import hashlib
import re
import unicodedata

from app.classifier.classifier import classify_topics
from app.config.logger import logger
from app.config.settings import settings
from app.database.classification_logs import insert_classification_log
from app.database.generated_tips import insert_generated_tip, is_duplicate
from app.database.topics import upsert_topics
from app.generator.generator import generate_sms
from app.tasks.prefetch_tasks import get_tip_from_pool
from app.validation.length import validate_length
from app.validation.safety import validate_safety

ALLOWED_LANGUAGES = {'en', 'sw'}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ''
    normalized = unicodedata.normalize('NFC', text).strip()
    normalized = re.sub(r'\s+', ' ', normalized).lower()
    normalized = ''.join(
        ch for ch in normalized
        if unicodedata.category(ch)[0] != 'P'
    )
    return re.sub(r'\s+', ' ', normalized).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode('utf-8')).hexdigest()


def _build_profile(classification: dict) -> dict:
    language = classification.get('language', 'sw') or 'sw'
    if language not in ALLOWED_LANGUAGES:
        logger.warning(
            'unsupported_language_detected',
            extra={
                'event':            'unsupported_language_detected',
                'detected_language': language,
                'fallback':         'sw',
            }
        )
        language = 'sw'

    topics = classification.get('topics', [])
    # Normalise: each item may be a plain string or a dict with a 'name' key
    topic_codes = [
        t.get('name') if isinstance(t, dict) else t
        for t in topics
    ] if topics else []

    return {'language': language, 'topics': topic_codes}


def _validate_and_store(msisdn: str, sms_text: str, language: str,
                        topics: list, validation_status: str):
    """Validate → dedup → persist as delivery_status='ready'."""
    length_ok, length_reason = validate_length(sms_text)
    safe_ok,   safe_reason   = validate_safety(sms_text)

    if not length_ok or not safe_ok:
        logger.warning(
            'validation_failure',
            extra={
                'event':         'validation_failure',
                'msisdn':        msisdn,
                'sms':           sms_text,
                'length_reason': length_reason,
                'safety_reason': safe_reason,
            }
        )
        # Pool tips are pre-validated — use one as last resort
        sms_text = get_tip_from_pool(language)
        validation_status = 'fallback'

        if not sms_text:
            logger.error(
                'no_valid_tip_available',
                extra={'event': 'no_valid_tip_available', 'msisdn': msisdn}
            )
            return

        length_ok, length_reason = validate_length(sms_text)
        safe_ok,   safe_reason   = validate_safety(sms_text)

    if not length_ok or not safe_ok:
        logger.error(
            'fallback_validation_failed',
            extra={
                'event':         'fallback_validation_failed',
                'msisdn':        msisdn,
                'sms':           sms_text,
                'length_reason': length_reason,
                'safety_reason': safe_reason,
            }
        )
        return

    tip_hash  = _sha256(sms_text)
    duplicate = False
    try:
        duplicate = is_duplicate(msisdn, tip_hash)
    except Exception as exc:
        logger.exception(
            'duplicate_check_failed',
            extra={'event': 'duplicate_check_failed', 'msisdn': msisdn, 'error': str(exc)}
        )

    if duplicate:
        try:
            insert_generated_tip(msisdn, topics, language, sms_text, tip_hash,
                                 'duplicate', 'skipped')
        except Exception as exc:
            logger.exception(
                'duplicate_log_failed',
                extra={'event': 'duplicate_log_failed', 'msisdn': msisdn, 'error': str(exc)}
            )
        return

    try:
        insert_generated_tip(msisdn, topics, language, sms_text, tip_hash,
                             validation_status, 'ready')
    except Exception as exc:
        logger.exception(
            'generated_tip_log_failed',
            extra={'event': 'generated_tip_log_failed', 'msisdn': msisdn, 'error': str(exc)}
        )


# ── Main task ─────────────────────────────────────────────────────────────────

def process_profile(msisdn: str, messages_by_period: dict):
    """Entry point called by the AI worker for each subscriber.

    Args:
        msisdn:             E.g. "255743956595"
        messages_by_period: {"last_24h": [...], "older": [...]}
    """
    last_24h = messages_by_period.get('last_24h', [])
    older    = messages_by_period.get('older', [])
    has_history = bool(last_24h or older)

    logger.info(
        'process_profile_started',
        extra={
            'event':          'process_profile_started',
            'msisdn':         msisdn,
            'last_24h_count': len(last_24h),
            'older_count':    len(older),
            'has_history':    has_history,
        }
    )

    # ── Path A: no chat history ───────────────────────────────────────────────
    # Use the pre-generated pool to avoid per-subscriber API calls.
    if not has_history:
        sms_text = get_tip_from_pool('sw')

        if not sms_text:
            logger.warning(
                'generic_pool_empty',
                extra={'event': 'generic_pool_empty', 'msisdn': msisdn}
            )
            try:
                sms_text = generate_sms({'language': 'sw', 'topics': []})
            except Exception as exc:
                logger.exception(
                    'on_demand_tip_failed',
                    extra={
                        'event':  'on_demand_tip_failed',
                        'msisdn': msisdn,
                        'error':  str(exc),
                    }
                )
                return

        _validate_and_store(
            msisdn,
            sms_text,
            language='sw',
            topics=[],
            validation_status='generic',
        )
        return

    # ── Path B: has chat history → classify + personalised tip ───────────────
    all_messages = last_24h + older
    raw_messages = '\n'.join(all_messages)

    classification = {'language': 'sw', 'topics': []}
    try:
        classification = classify_topics(messages_by_period)
    except Exception as exc:
        logger.exception(
            'classification_failed',
            extra={'event': 'classification_failed', 'msisdn': msisdn, 'error': str(exc)}
        )

    language = classification.get('language', 'sw') or 'sw'
    topics   = classification.get('topics', [])

    logger.info(
        'classification_result',
        extra={
            'event':    'classification_result',
            'msisdn':   msisdn,
            'language': language,
            'topics':   topics,
        }
    )

    try:
        insert_classification_log(msisdn, raw_messages, language, topics, settings.OPENAI_MODEL)
    except Exception as exc:
        logger.exception(
            'classification_log_failed',
            extra={'event': 'classification_log_failed', 'msisdn': msisdn, 'error': str(exc)}
        )

    profile = _build_profile(classification)

    if profile.get('topics'):
        try:
            upsert_topics(profile['topics'])
        except Exception as exc:
            logger.exception(
                'topics_upsert_failed',
                extra={
                    'event':  'topics_upsert_failed',
                    'msisdn': msisdn,
                    'topics': profile.get('topics'),
                    'error':  str(exc),
                }
            )

    sms_text          = None
    validation_status = 'ok'

    try:
        sms_text = generate_sms(profile)
    except Exception as exc:
        logger.exception(
            'sms_generation_failed',
            extra={
                'event':   'sms_generation_failed',
                'msisdn':  msisdn,
                'profile': profile,
                'error':   str(exc),
            }
        )
        sms_text          = get_tip_from_pool(language)
        validation_status = 'fallback'

    if not sms_text:
        sms_text          = get_tip_from_pool(language)
        validation_status = 'fallback'

    if not sms_text:
        logger.error(
            'no_sms_text_available',
            extra={'event': 'no_sms_text_available', 'msisdn': msisdn, 'language': language}
        )
        return

    _validate_and_store(msisdn, sms_text, language, profile.get('topics', []), validation_status)
