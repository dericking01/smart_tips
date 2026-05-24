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


def fetch_ready_tips():
    """Return all tips prepared in the current dispatch window (last 3 hours).
    Ordered oldest-first so earlier-prepared subscribers are sent first.
    Columns: (id, msisdn, language, generated_tip)
    """
    session = SessionLocal()
    query = text("""
        SELECT id, msisdn, language, generated_tip
        FROM smart_tips.generated_tips
        WHERE delivery_status = 'ready'
        AND created_at >= NOW() - INTERVAL '3 hours'
        ORDER BY created_at ASC
    """)
    rows = session.execute(query).fetchall()
    session.close()
    return rows


def update_delivery_status(tip_id, status):
    """Update the delivery_status of a single tip after a dispatch attempt."""
    session = SessionLocal()
    query = text("""
        UPDATE smart_tips.generated_tips
        SET delivery_status = :status
        WHERE id = :tip_id
    """)
    session.execute(query, {"tip_id": tip_id, "status": status})
    session.commit()
    session.close()


def fetch_failed_tips(max_retries: int = 2, window_hours: int = 2):
    """Return failed tips from the current window that are still eligible for retry.
    Columns: (id, msisdn, language, generated_tip)
    """
    session = SessionLocal()
    q = text(f"""
        SELECT id, msisdn, language, generated_tip
        FROM smart_tips.generated_tips
        WHERE delivery_status = 'failed'
        AND retry_count < :max_retries
        AND created_at >= NOW() - INTERVAL '{int(window_hours)} hours'
        ORDER BY created_at ASC
    """)
    rows = session.execute(q, {"max_retries": max_retries}).fetchall()
    session.close()
    return rows


def increment_retry_count(tip_id):
    """Increment retry_count after a failed retry attempt (keeps delivery_status='failed')."""
    session = SessionLocal()
    query = text("""
        UPDATE smart_tips.generated_tips
        SET retry_count = retry_count + 1
        WHERE id = :tip_id
    """)
    session.execute(query, {"tip_id": tip_id})
    session.commit()
    session.close()
