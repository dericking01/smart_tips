"""
aggregator.py

Aggregates raw chat.chat_history rows into a per-subscriber dict that
separates messages by recency:

    {
        "255743956595": {
            "last_24h": ["Kwani figo ni nn", "Magonjwa ya figo ni nn"],
            "older":    []                   # messages from 24–48 h ago
        },
        ...
    }

The recency split lets the classifier prioritise topics that appeared in
the most recent conversation window (last 24 h), matching the business
rule: "if topic scores are close, prefer the latest 24h chat history."

Session ID format:  {msisdn}-{dd}-{mm}-{yyyy}
e.g.               255743956595-24-05-2026
"""

from collections import defaultdict
from datetime import datetime

from app.conversations.parser import parse_message


def aggregate_conversations(rows: list) -> dict:
    """
    Returns:
        {msisdn: {"last_24h": [...], "older": [...]}}

    last_24h — messages whose session date matches TODAY's calendar date.
    older    — messages from any earlier date in the 48-hour window.
    """
    today_str = datetime.now().strftime('%d-%m-%Y')

    grouped: dict = defaultdict(lambda: {'last_24h': [], 'older': []})

    for session_id, message in rows:
        # session_id = "255743956595-24-05-2026"
        # Split only on the FIRST dash to isolate msisdn from the date part
        parts = session_id.split('-', 1)
        if len(parts) != 2:
            continue

        msisdn, date_str = parts[0].strip(), parts[1].strip()

        parsed = parse_message(message)
        if not parsed:
            continue
        if parsed.get('type') != 'human':
            continue

        content = parsed.get('content', '').strip()
        if not content:
            continue

        bucket = 'last_24h' if date_str == today_str else 'older'
        grouped[msisdn][bucket].append(content)

    return grouped
