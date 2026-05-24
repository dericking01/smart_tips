import hashlib
import re
import traceback
import unicodedata
from app.classifier.classifier import classify_topics
from app.config.logger import logger
from app.config.settings import settings
from app.database.classification_logs import insert_classification_log
from app.database.generated_tips import insert_generated_tip, is_duplicate
from app.database.topics import upsert_topics
from app.generator.generator import generate_sms
from app.queue.redis_client import sms_queue
from app.tasks.prefetch_tasks import get_tip_from_pool
from app.validation.length import validate_length
from app.validation.safety import validate_safety

ALLOWED_LANGUAGES = {'en', 'sw'}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_text(text):
    if not isinstance(text, str):
        return ''
    normalized = unicodedata.normalize('NFC', text).strip()
    normalized = re.sub(r'\s+', ' ', normalized).lower()
    normalized = ''.join(
        ch for ch in normalized
        if unicodedata.category(ch)[0] != 'P'
    )
    return re.sub(r'\s+', ' ', normalized).strip()


def _sha256(text):
    return hashlib.sha256(_normalize_text(text).encode('utf-8')).hexdigest()


def _build_profile(classification):
    language = classification.get('language', 'sw') or 'sw'
    if language not in ALLOWED_LANGUAGES:
        logger.warning(
            'unsupported_language_detected',
            extra={
                'event': 'unsupported_language_detected',
                'detected_language': language,
                'fallback': 'sw'
            }
        )
        language = 'sw'
    topics = classification.get('topics', [])
    return {
        'language': language,
        'topics': [t.get('name') if isinstance(t, dict) else t for t in topics] if topics else []
    }


def _validate_and_dispatch(msisdn, sms_text, language, topics, validation_status):
    """Validate → dedup → persist → enqueue. Shared by both processing paths."""
    length_ok, length_reason = validate_length(sms_text)
    safe_ok, safe_reason = validate_safety(sms_text)

    if not length_ok or not safe_ok:
        logger.warning(
            'validation_failure',
            extra={
                'event': 'validation_failure',
                'msisdn': msisdn,
                'sms': sms_text,
                'length_reason': length_reason,
                'safety_reason': safe_reason
            }
        )
        # Pool tips were pre-validated, so this is a genuine last resort
        sms_text = get_tip_from_pool(language)
        validation_status = 'fallback'

        if not sms_text:
            logger.error(
                'no_valid_tip_available',
                extra={'event': 'no_valid_tip_available', 'msisdn': msisdn}
            )
            return

        length_ok, length_reason = validate_length(sms_text)
        safe_ok, safe_reason = validate_safety(sms_text)

    if not length_ok or not safe_ok:
        logger.error(
            'fallback_validation_failed',
            extra={
                'event': 'fallback_validation_failed',
                'msisdn': msisdn,
                'sms': sms_text,
                'length_reason': length_reason,
                'safety_reason': safe_reason
            }
        )
        return

    tip_hash = _sha256(sms_text)
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
            insert_generated_tip(msisdn, topics, language, sms_text, tip_hash, 'duplicate', 'skipped')
        except Exception as exc:
            logger.exception(
                'duplicate_log_failed',
                extra={'event': 'duplicate_log_failed', 'msisdn': msisdn, 'error': str(exc)}
            )
        return

    try:
        insert_generated_tip(msisdn, topics, language, sms_text, tip_hash, validation_status, 'queued')
    except Exception as exc:
        logger.exception(
            'generated_tip_log_failed',
            extra={'event': 'generated_tip_log_failed', 'msisdn': msisdn, 'error': str(exc)}
        )

    try:
        sms_queue.enqueue('app.tasks.retry_tasks.retry_send_sms', msisdn, sms_text)
    except Exception as exc:
        logger.exception(
            'enqueue_sms_failed',
            extra={'event': 'enqueue_sms_failed', 'msisdn': msisdn, 'error': str(exc)}
        )
        traceback.print_exc()


# ── Main task ─────────────────────────────────────────────────────────────────

def process_profile(msisdn, messages):

    # ── Path A: no chat history ───────────────────────────────────────────────
    # Skip the full AI pipeline. Use the pre-generated pool so all no-history
    # subscribers are served with a single batch API call per schedule run.
    if not messages:
        sms_text = get_tip_from_pool('sw')

        if not sms_text:
            # Pool unavailable (e.g. prefetch job failed); generate on-demand.
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
                        'event': 'on_demand_tip_failed',
                        'msisdn': msisdn,
                        'error': str(exc)
                    }
                )
                return

        _validate_and_dispatch(
            msisdn,
            sms_text,
            language='sw',
            topics=[],
            validation_status='generic'
        )
        return

    # ── Path B: has chat history → classify + personalised tip ───────────────
    raw_messages = '\n'.join(messages)
    classification = {'language': 'sw', 'topics': []}

    try:
        classification = classify_topics(messages)
    except Exception as exc:
        logger.exception(
            'classification_failed',
            extra={'event': 'classification_failed', 'msisdn': msisdn, 'error': str(exc)}
        )

    language = classification.get('language', 'sw') or 'sw'
    topics = classification.get('topics', [])

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
                    'event': 'topics_upsert_failed',
                    'msisdn': msisdn,
                    'topics': profile.get('topics'),
                    'error': str(exc)
                }
            )

    sms_text = None
    validation_status = 'ok'

    try:
        sms_text = generate_sms(profile)
    except Exception as exc:
        logger.exception(
            'sms_generation_failed',
            extra={
                'event': 'sms_generation_failed',
                'msisdn': msisdn,
                'profile': profile,
                'error': str(exc)
            }
        )
        sms_text = get_tip_from_pool(language)
        validation_status = 'fallback'

    if not sms_text:
        sms_text = get_tip_from_pool(language)
        validation_status = 'fallback'

    if not sms_text:
        logger.error(
            'no_sms_text_available',
            extra={'event': 'no_sms_text_available', 'msisdn': msisdn, 'language': language}
        )
        return

    _validate_and_dispatch(msisdn, sms_text, language, profile.get('topics', []), validation_status)
