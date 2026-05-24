from sqlalchemy import text
from app.database.postgres import SessionLocal
from app.config.logger import logger
from datetime import datetime, timedelta


def fetch_recent_conversations():
    """Fetch all human chat messages from the past 48 hours.

    Covers today + yesterday + the day before yesterday so that even at
    midnight the full 48-hour window is always populated.

    Session IDs are keyed as  {msisdn}-{dd}-{mm}-{yyyy}
    e.g.  255743956595-24-05-2026
    """
    session = SessionLocal()
    today = datetime.now()

    # Three day-patterns guarantee true 48-hour coverage at any time of day
    patterns = {
        f"day{i}": f"%-{(today - timedelta(days=i)).strftime('%d-%m-%Y')}"
        for i in range(3)
    }

    query = text("""
        SELECT session_id, message
        FROM chat.chat_history
        WHERE session_id LIKE :day0
           OR session_id LIKE :day1
           OR session_id LIKE :day2
    """)

    rows = session.execute(query, patterns).fetchall()
    session.close()

    logger.info(
        'chat_history_fetched',
        extra={
            'event': 'chat_history_fetched',
            'patterns': list(patterns.values()),
            'row_count': len(rows),
        }
    )
    return rows
