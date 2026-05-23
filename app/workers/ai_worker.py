from rq import Worker, Queue, Connection
from app.queue.redis_client import redis_conn

listen = ['ai_generation_queue']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        worker.work()