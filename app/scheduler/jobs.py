from app.database.subscriptions import fetch_active_subscribers
from app.database.chat_history import fetch_recent_conversations
from app.conversations.aggregator import aggregate_conversations
from app.classifier.classifier import classify_topics
from app.generator.generator import generate_sms
from app.validation.length import validate_length
from app.validation.safety import validate_safety
from app.sms.sender import send_sms

def process_smart_tips_job():
    subscribers = fetch_active_subscribers()

    rows = fetch_recent_conversations()

    grouped = aggregate_conversations(rows)

    for msisdn in subscribers:
        messages = grouped.get(msisdn, [])

        profile = {
            "language": "sw",
            "topics": ["general_health"]
        }

        if messages:
            profile = classify_topics(messages)

        sms = generate_sms(profile)

        if not validate_length(sms):
            continue

        if not validate_safety(sms):
            continue

        send_sms(msisdn, sms)