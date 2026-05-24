from apscheduler.schedulers.blocking import BlockingScheduler
from zoneinfo import ZoneInfo
from app.scheduler.jobs import prefetch_generic_tips_job, process_smart_tips_job
from app.config.settings import settings

# Use configured timezone (default Africa/Dar_es_Salaam)
try:
    tz = ZoneInfo(settings.TIMEZONE)
except Exception:
    tz = settings.TIMEZONE

scheduler = BlockingScheduler(timezone=tz)

# ── Run 1: morning ────────────────────────────────────────────────────────────
# Prefetch generic tips pool 5 minutes before the main job so the pool is
# always warm when process_smart_tips_job starts enqueueing tasks.
scheduler.add_job(prefetch_generic_tips_job, 'cron', hour=6, minute=45)
scheduler.add_job(process_smart_tips_job,    'cron', hour=6, minute=50)

# ── Run 2: mid-morning ────────────────────────────────────────────────────────
scheduler.add_job(prefetch_generic_tips_job, 'cron', hour=13, minute=17)
scheduler.add_job(process_smart_tips_job,    'cron', hour=13, minute=23)


def start_scheduler():
    scheduler.start()