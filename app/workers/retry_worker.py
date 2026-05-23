from rq import Worker, Queue, Connection
from app.queue.redis_client import redis_conn, retry_queue

listen = ['retry_queue']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        worker.work()
