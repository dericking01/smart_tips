import csv
import os

from app.config.logger import logger

# UAT: subscribers are loaded from a local CSV instead of the database.
# Switch back to the DB query when merging to production.
_UAT_CSV_PATH = os.path.join(
    os.path.dirname(__file__),          # app/database/
    '..', '..', 'public', 'assets',    # → project root / public / assets
    'uat_subscribers.csv'
)


def fetch_active_subscribers() -> list[str]:
    """Return a list of active subscriber MSISDNs.

    UAT mode: reads from public/assets/uat_subscribers.csv
    Production: query subscription.subscriptions WHERE status='ACTIVE'
    """
    csv_path = os.path.normpath(_UAT_CSV_PATH)

    try:
        with open(csv_path, newline='') as fh:
            reader = csv.DictReader(fh)
            msisdns = [row['msisdn'].strip() for row in reader if row.get('msisdn', '').strip()]

        logger.info(
            'uat_subscribers_loaded',
            extra={
                'event': 'uat_subscribers_loaded',
                'count': len(msisdns),
                'source': csv_path,
            }
        )
        return msisdns

    except FileNotFoundError:
        logger.error(
            'uat_csv_not_found',
            extra={'event': 'uat_csv_not_found', 'path': csv_path}
        )
        return []
    except Exception as exc:
        logger.exception(
            'uat_csv_read_error',
            extra={'event': 'uat_csv_read_error', 'error': str(exc)}
        )
        return []
