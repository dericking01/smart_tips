import json


def parse_message(raw_message):
    """Parse a chat message into a dict.

    chat.chat_history stores the 'message' column as JSONB.
    SQLAlchemy + psycopg2 deserialises JSONB columns automatically, so
    raw_message arrives as a Python dict — not a string.

    We handle both forms so the function is safe regardless of the column
    type (TEXT vs JSONB) or future schema changes.
    """
    if isinstance(raw_message, dict):
        return raw_message          # JSONB → already a dict, use as-is

    if isinstance(raw_message, str):
        try:
            return json.loads(raw_message)   # TEXT → deserialise manually
        except (json.JSONDecodeError, ValueError):
            return None

    return None                     # unexpected type → skip
