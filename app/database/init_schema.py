from sqlalchemy import text
from app.database.postgres import engine

def init_schema():
    with open("sql/init_schema.sql", "r") as file:
        sql = file.read()

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()