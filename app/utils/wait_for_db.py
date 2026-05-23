import time
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.database.postgres import engine
from app.config.logger import logger


def wait_for_db(retries=30, delay=2):
    attempt = 0
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            logger.info('db_available', extra={'event': 'db_available'})
            return True
        except OperationalError as exc:
            attempt += 1
            logger.warning('db_unavailable', extra={'event': 'db_unavailable', 'attempt': attempt, 'error': str(exc)})
            if retries and attempt >= retries:
                logger.error('db_wait_timeout', extra={'event': 'db_wait_timeout'})
                raise
            time.sleep(delay)


if __name__ == '__main__':
    wait_for_db(retries=0, delay=2)
