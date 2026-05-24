from sqlalchemy import text
from app.database.postgres import SessionLocal


def upsert_topics(topic_codes: list):
    """Insert AI-discovered topic codes into smart_tips.topics.
    Derives topic_name from the code (e.g. 'blood_pressure' → 'Blood Pressure').
    Skips codes that already exist.
    """
    if not topic_codes:
        return

    session = SessionLocal()
    try:
        for code in topic_codes:
            topic_name = code.replace('_', ' ').title()
            session.execute(
                text("""
                    INSERT INTO smart_tips.topics (topic_code, topic_name, is_active)
                    VALUES (:code, :name, TRUE)
                    ON CONFLICT (topic_code) DO NOTHING
                """),
                {"code": code, "name": topic_name}
            )
        session.commit()
    finally:
        session.close()
