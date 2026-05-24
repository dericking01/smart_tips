from sqlalchemy import text
from app.database.postgres import SessionLocal


def insert_sms_log(msisdn, message_text, status, port=None, error=None, attempt=1, response_code=None):
    session = SessionLocal()

    query = text("""
        INSERT INTO smart_tips.sms_logs
            (msisdn, message_text, status, port, error, attempt, response_code)
        VALUES
            (:msisdn, :message_text, :status, :port, :error, :attempt, :response_code)
    """)

    session.execute(query, {
        "msisdn": msisdn,
        "message_text": message_text,
        "status": status,
        "port": port,
        "error": error,
        "attempt": attempt,
        "response_code": response_code
    })
    session.commit()
    session.close()
