from rq import Worker, Queue
from app.queue.redis_client import redis_conn

listen = ['ai_generation_queue']

if __name__ == '__main__':
    queues = [Queue(name, connection=redis_conn) for name in listen]
    worker = Worker(queues, connection=redis_conn)
    worker.work()