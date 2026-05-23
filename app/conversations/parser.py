import json

def parse_message(raw_message):
    try:
        return json.loads(raw_message)
    except Exception:
        return None