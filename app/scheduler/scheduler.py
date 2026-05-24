from apscheduler.schedulers.blocking import BlockingScheduler
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.scheduler.jobs import (
    dispatch_tips_job,
    prefetch_pool_job,
    prepare_all_tips_job,
    prepare_late_subscribers_job,
    retry_failed_tips_job,
)

try:
    tz = ZoneInfo(settings.TIMEZONE)
except Exception:
    tz = settings.TIMEZONE

scheduler = BlockingScheduler(timezone=tz)

# ══════════════════════════════════════════════════════════════════════════════
#  MORNING WINDOW  —  send at 07:00
# ══════════════════════════════════════════════════════════════════════════════
#
#  06:00  prefetch_pool_job
#           One OpenAI batch call → 10 sw + 10 en generic tips → Redis.
#           Pool is warm before AI workers start.
#
#  06:10  prepare_all_tips_job
#           Enqueues process_profile() for every active subscriber.
#           AI workers classify + generate in parallel (~45 min window).
#           • has chat history  → personalised tip  → DB 'ready'
#           • no chat history   → random pool tip   → DB 'ready'
#           Each msisdn is added to a Redis window-set for late-catch tracking.
#
#  06:55  prepare_late_subscribers_job
#           Re-queries subscriber list. Any msisdn NOT in the window-set
#           (new subs who joined 06:10–06:55) is enqueued for processing.
#
#  07:00  dispatch_tips_job
#           SELECT delivery_status='ready' → send at 200 TPS round-robin
#           across SMS ports with per-port failover.
#           Updates each row to 'sent' or 'failed'.
#
# ══════════════════════════════════════════════════════════════════════════════

scheduler.add_job(prefetch_pool_job,            'cron', hour=6,  minute=0)
scheduler.add_job(prepare_all_tips_job,         'cron', hour=6,  minute=10)
scheduler.add_job(prepare_late_subscribers_job, 'cron', hour=6,  minute=55)
scheduler.add_job(dispatch_tips_job,            'cron', hour=7,  minute=0)
scheduler.add_job(retry_failed_tips_job,        'cron', hour=7,  minute=15)  # retry attempt 1
scheduler.add_job(retry_failed_tips_job,        'cron', hour=7,  minute=30)  # retry attempt 2

# ══════════════════════════════════════════════════════════════════════════════
#  EVENING WINDOW  —  send at 19:00
# ══════════════════════════════════════════════════════════════════════════════

scheduler.add_job(prefetch_pool_job,            'cron', hour=18, minute=0)
scheduler.add_job(prepare_all_tips_job,         'cron', hour=18, minute=10)
scheduler.add_job(prepare_late_subscribers_job, 'cron', hour=18, minute=55)
scheduler.add_job(dispatch_tips_job,            'cron', hour=19, minute=0)
scheduler.add_job(retry_failed_tips_job,        'cron', hour=19, minute=15)  # retry attempt 1
scheduler.add_job(retry_failed_tips_job,        'cron', hour=19, minute=30)  # retry attempt 2


def start_scheduler():
    scheduler.start()
