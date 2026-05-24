from app.tasks.dispatch_tasks import dispatch_all_ready_tips, retry_failed_tips
from app.tasks.generation_tasks import prepare_all_tips, prepare_late_subscribers
from app.tasks.prefetch_tasks import prefetch_generic_tips


def prefetch_pool_job():
    """Generate and cache the generic tips pool (sw + en) in Redis.
    Runs first so the pool is warm before AI workers start pulling from it.
    """
    prefetch_generic_tips()


def prepare_all_tips_job():
    """Enqueue AI processing for all active subscribers.
    Runs ~50 min before dispatch to give AI workers enough time.
    """
    prepare_all_tips()


def prepare_late_subscribers_job():
    """Catch new subscribers who joined after prepare_all_tips_job ran.
    Runs ~5 min before dispatch as a final sweep.
    """
    prepare_late_subscribers()


def dispatch_tips_job():
    """Send all ready tips at SMS_TPS (200 TPS) round-robin across SMS ports.
    Runs at exactly the send window (07:00 and 19:00).
    """
    dispatch_all_ready_tips()


def retry_failed_tips_job():
    """Retry tips that failed during dispatch (all ports were unavailable).
    Runs twice per window (+15 min and +30 min after dispatch).
    Each run increments retry_count; tips exceeding MAX_RETRIES are abandoned.
    """
    retry_failed_tips()
