import redis
from rq import Queue
from app.config.settings import settings

redis_conn = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT
)

ai_queue = Queue("ai_generation_queue", connection=redis_conn)
sms_queue = Queue("sms_dispatch_queue", connection=redis_conn)
retry_queue = Queue("retry_queue", connection=redis_conn)