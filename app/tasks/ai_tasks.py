import json
import hashlib
import traceback
from app.classifier.classifier import classify_topics
from app.generator.generator import generate_sms
from app.validation.length import validate_length
from app.validation.safety import validate_safety
from app.database.classification_logs import insert_classification_log
from app.database.generated_tips import insert_generated_tip, is_duplicate
from app.queue.redis_client import sms_queue

FALLBACK_SMS = {
    "sw": "Afya ni muhimu. Kula vizuri, kunywa maji mengi, na pata usingizi wa kutosha kila siku.",
    "en": "Keep healthy: eat well, stay hydrated, and get enough sleep every day."
}


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def process_profile(msisdn, messages):
    raw_messages = "\n".join(messages) if messages else ""

    # Step 1: classify
    try:
        classification = classify_topics(messages) if messages else {"language": "sw", "topics": []}
    except Exception:
        classification = {"language": "sw", "topics": []}

    language = classification.get('language', 'sw')
    topics = classification.get('topics', [])

    # Persist classification log
    try:
        insert_classification_log(msisdn, raw_messages, language, topics, None)
    except Exception:
        pass

    # Build profile for generation
    profile = {
        "language": language,
        "topics": [t.get('name') if isinstance(t, dict) else t for t in topics] if topics else []
    }

    # Step 2: generate SMS
    try:
        sms = generate_sms(profile)
    except Exception:
        sms = FALLBACK_SMS.get(language, FALLBACK_SMS["sw"])

    # Validation
    valid_len = validate_length(sms)
    valid_safe = validate_safety(sms)

    tip_hash = _sha256(sms)

    # Duplicate check
    try:
        duplicate = is_duplicate(msisdn, tip_hash)
    except Exception:
        duplicate = False

    if duplicate:
        # Persist as skipped duplicate
        try:
            insert_generated_tip(msisdn, profile.get('topics'), language, sms, tip_hash, 'duplicate', 'skipped')
        except Exception:
            pass
        return

    if not (valid_len and valid_safe):
        # Use fallback if validation fails
        sms = FALLBACK_SMS.get(language, FALLBACK_SMS["sw"])
        tip_hash = _sha256(sms)
        # Re-check duplicate for fallback
        try:
            duplicate = is_duplicate(msisdn, tip_hash)
        except Exception:
            duplicate = False

        if duplicate:
            try:
                insert_generated_tip(msisdn, profile.get('topics'), language, sms, tip_hash, 'duplicate', 'skipped')
            except Exception:
                pass
            return

        validation_status = 'fallback' if not (valid_len and valid_safe) else 'ok'
    else:
        validation_status = 'ok'

    # Persist generated tip with queued status
    try:
        insert_generated_tip(msisdn, profile.get('topics'), language, sms, tip_hash, validation_status, 'queued')
    except Exception:
        pass

    # Enqueue SMS send
    try:
        sms_queue.enqueue('app.sms.sender.send_sms', msisdn, sms)
    except Exception:
        traceback.print_exc()
