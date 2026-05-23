from apscheduler.schedulers.blocking import BlockingScheduler
from zoneinfo import ZoneInfo
from app.scheduler.jobs import process_smart_tips_job
from app.config.settings import settings

# Use configured timezone (default Africa/Dar_es_Salaam)
try:
    tz = ZoneInfo(settings.TIMEZONE)
except Exception:
    tz = settings.TIMEZONE

scheduler = BlockingScheduler(timezone=tz)

scheduler.add_job(
    process_smart_tips_job,
    'cron',
    hour=6,
    minute=50
)

scheduler.add_job(
    process_smart_tips_job,
    'cron',
    hour=19,
    minute=17
)

def start_scheduler():
    scheduler.start()