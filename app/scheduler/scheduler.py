from apscheduler.schedulers.blocking import BlockingScheduler
from app.scheduler.jobs import process_smart_tips_job

scheduler = BlockingScheduler()

scheduler.add_job(
    process_smart_tips_job,
    'cron',
    hour=6,
    minute=50
)

scheduler.add_job(
    process_smart_tips_job,
    'cron',
    hour=18,
    minute=50
)

def start_scheduler():
    scheduler.start()