import hashlib
import re
import traceback
import unicodedata
from app.classifier.classifier import classify_topics
from app.config.logger import logger
from app.config.settings import settings
from app.database.classification_logs import insert_classification_log
from app.database.generated_tips import insert_generated_tip, is_duplicate
from app.generator.generator import generate_sms
from app.queue.redis_client import sms_queue
from app.validation.length import validate_length
from app.validation.safety import validate_safety

FALLBACK_SMS = {
    "sw": [
        "Afya ni muhimu. Kula vizuri, kunywa maji mengi, na pata usingizi wa kutosha kila siku.",
        "Msongamano wa mawazo upungue kwa kupumzika vizuri, kunywa maji, na kula vyakula bora.",
        "Huduma ya afya huanza kwa kula vizuri, kunywa maji na kupata usingizi wa kutosha kila usiku."
    ],
    "en": [
        "Stay healthy: eat balanced meals, drink enough water, and get regular sleep.",
        "Preventive health begins with good nutrition, hydration, and daily rest.",
        "Healthy habits like drinking water, sleeping well, and moving daily support wellbeing."
    ]
}


def _normalize_text(text):
    if not isinstance(text, str):
        return ''

    normalized = unicodedata.normalize('NFC', text)
    normalized = normalized.strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.lower()
    normalized = ''.join(
        ch for ch in normalized
        if unicodedata.category(ch)[0] != 'P'
    )
    normalized = normalized.strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def _sha256(text):
    normalized_text = _normalize_text(text)
    return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()


def _get_fallback_sms(language):
    choices = FALLBACK_SMS.get(language, FALLBACK_SMS.get('en'))
    return choices[0] if isinstance(choices, list) else choices


ALLOWED_LANGUAGES = {'en', 'sw'}


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


def process_profile(msisdn, messages):
    raw_messages = '\n'.join(messages) if messages else ''
    classification = {'language': 'sw', 'topics': []}

    if messages:
        try:
            classification = classify_topics(messages)
        except Exception as exc:
            logger.exception(
                'classification_failed',
                extra={
                    'event': 'classification_failed',
                    'msisdn': msisdn,
                    'error': str(exc)
                }
            )

    language = classification.get('language', 'sw') or 'sw'
    topics = classification.get('topics', [])

    try:
        insert_classification_log(msisdn, raw_messages, language, topics, settings.OPENAI_MODEL)
    except Exception as exc:
        logger.exception(
            'classification_log_failed',
            extra={
                'event': 'classification_log_failed',
                'msisdn': msisdn,
                'error': str(exc)
            }
        )

    profile = _build_profile(classification)
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
        sms_text = _get_fallback_sms(language)
        validation_status = 'fallback'

    if not sms_text:
        sms_text = _get_fallback_sms(language)
        validation_status = 'fallback'

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
        sms_text = _get_fallback_sms(language)
        validation_status = 'fallback'
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
            extra={
                'event': 'duplicate_check_failed',
                'msisdn': msisdn,
                'error': str(exc)
            }
        )

    if duplicate:
        try:
            insert_generated_tip(msisdn, profile.get('topics'), language, sms_text, tip_hash, 'duplicate', 'skipped')
        except Exception as exc:
            logger.exception(
                'duplicate_log_failed',
                extra={
                    'event': 'duplicate_log_failed',
                    'msisdn': msisdn,
                    'error': str(exc)
                }
            )
        return

    try:
        insert_generated_tip(msisdn, profile.get('topics'), language, sms_text, tip_hash, validation_status, 'queued')
    except Exception as exc:
        logger.exception(
            'generated_tip_log_failed',
            extra={
                'event': 'generated_tip_log_failed',
                'msisdn': msisdn,
                'error': str(exc)
            }
        )

    try:
        sms_queue.enqueue(
            'app.tasks.retry_tasks.retry_send_sms',
            msisdn,
            sms_text
        )
    except Exception as exc:
        logger.exception(
            'enqueue_sms_failed',
            extra={
                'event': 'enqueue_sms_failed',
                'msisdn': msisdn,
                'error': str(exc)
            }
        )
        traceback.print_exc()
