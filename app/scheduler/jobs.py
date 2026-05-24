from app.database.subscriptions import fetch_active_subscribers
from app.database.chat_history import fetch_recent_conversations
from app.conversations.aggregator import aggregate_conversations
from app.queue.redis_client import ai_queue
from app.tasks.prefetch_tasks import prefetch_generic_tips


def prefetch_generic_tips_job():
    """Run once per schedule, before process_smart_tips_job.
    Generates and caches a pool of generic tips so no-history subscribers
    are served without an individual OpenAI call each.
    """
    prefetch_generic_tips()


def process_smart_tips_job():
    subscribers = fetch_active_subscribers()

    rows = fetch_recent_conversations()

    grouped = aggregate_conversations(rows)

    for msisdn in subscribers:
        messages = grouped.get(msisdn, [])

        try:
            ai_queue.enqueue('app.tasks.ai_tasks.process_profile', msisdn, messages)
        except Exception:
            # best-effort: continue to next subscriber
            continue
