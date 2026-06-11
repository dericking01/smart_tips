from sqlalchemy import text
from app.database.postgres import SessionLocal

def fetch_active_subscribers():
    session = SessionLocal()

    query = text("""
        SELECT customer_msisdn
        FROM subscription.subscriptions
        WHERE status='ACTIVE'
        AND plan_code='921465_P02'
    """)

    rows = session.execute(query).fetchall()
    session.close()

    return [row[0] for row in rows]