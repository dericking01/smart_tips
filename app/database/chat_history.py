from sqlalchemy import text
from app.database.postgres import SessionLocal
from datetime import datetime, timedelta

def fetch_recent_conversations():
    session = SessionLocal()

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    patterns = [
        f"%-{today.strftime('%d-%m-%Y')}",
        f"%-{yesterday.strftime('%d-%m-%Y')}"
    ]

    query = text("""
        SELECT session_id, message
        FROM chat.chat_history
        WHERE session_id LIKE :today
        OR session_id LIKE :yesterday
    """)

    rows = session.execute(query, {
        "today": patterns[0],
        "yesterday": patterns[1]
    }).fetchall()

    session.close()
    return rows