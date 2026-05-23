import json
from sqlalchemy import text
from app.database.postgres import SessionLocal


def insert_classification_log(msisdn, raw_messages, language, topics, classifier_model):
    session = SessionLocal()

    query = text("""
        INSERT INTO smart_tips.classification_logs
            (msisdn, raw_messages, language, topics, classifier_model)
        VALUES
            (:msisdn, :raw_messages, :language, CAST(:topics AS JSONB), :classifier_model)
    """)

    session.execute(query, {
        "msisdn": msisdn,
        "raw_messages": raw_messages,
        "language": language,
        "topics": json.dumps(topics),
        "classifier_model": classifier_model
    })

    session.commit()
    session.close()
