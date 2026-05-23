import json
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import text
from app.database.postgres import SessionLocal


def insert_generated_tip(msisdn, topics, language, generated_tip, tip_hash,
                         validation_status, delivery_status):
    session = SessionLocal()

    query = text("""
        INSERT INTO smart_tips.generated_tips
            (msisdn, topics, language, generated_tip, tip_hash, validation_status, delivery_status)
        VALUES
            (:msisdn, CAST(:topics AS JSONB), :language, :generated_tip, :tip_hash, :validation_status, :delivery_status)
    """)

    session.execute(query, {
        "msisdn": msisdn,
        "topics": json.dumps(topics),
        "language": language,
        "generated_tip": generated_tip,
        "tip_hash": tip_hash,
        "validation_status": validation_status,
        "delivery_status": delivery_status
    })

    session.commit()
    session.close()


def is_duplicate(msisdn, tip_hash, days=7):
    session = SessionLocal()

    query = text("""
        SELECT 1 FROM smart_tips.generated_tips
        WHERE msisdn = :msisdn
        AND tip_hash = :tip_hash
        AND created_at >= (NOW() - INTERVAL ':days days')
        LIMIT 1
    """)

    # SQLAlchemy will not substitute :days into INTERVAL directly, so build query string
    q = text(query.text.replace(':days', str(int(days))))

    rows = session.execute(q, {"msisdn": msisdn, "tip_hash": tip_hash}).fetchall()

    session.close()

    return len(rows) > 0
