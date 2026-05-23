from app.database.subscriptions import fetch_active_subscribers
from app.database.chat_history import fetch_recent_conversations
from app.conversations.aggregator import aggregate_conversations
from app.queue.redis_client import ai_queue


def process_smart_tips_job():
    subscribers = fetch_active_subscribers()

    rows = fetch_recent_conversations()

    grouped = aggregate_conversations(rows)

    for msisdn in subscribers:
        messages = grouped.get(msisdn, [])

        # Enqueue an AI processing task for every subscriber (fallback if no messages)
        try:
            ai_queue.enqueue('app.tasks.ai_tasks.process_profile', msisdn, messages)
        except Exception:
            # best-effort: continue to next subscriber
            continue
