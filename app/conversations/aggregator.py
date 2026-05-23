from collections import defaultdict
from app.conversations.parser import parse_message

def aggregate_conversations(rows):
    grouped = defaultdict(list)

    for session_id, message in rows:
        msisdn = session_id.split("-")[0]

        parsed = parse_message(message)

        if not parsed:
            continue

        if parsed.get("type") != "human":
            continue

        grouped[msisdn].append(parsed.get("content"))

    return grouped