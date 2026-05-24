import json

from openai import OpenAI

from app.classifier.prompts import CLASSIFIER_PROMPT
from app.config.logger import logger
from app.config.settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def classify_topics(messages_by_period: dict) -> dict:
    """Classify health topics from a subscriber's recent chat history.

    Args:
        messages_by_period: {
            "last_24h": ["msg1", "msg2"],   # today's human messages
            "older":    ["msg3"],            # 24–48 h ago human messages
        }

    Returns:
        {"language": "sw"|"en", "topics": ["topic_code", ...]}
        Topics are ordered highest-priority first.
    """
    last_24h: list = messages_by_period.get('last_24h', [])
    older: list    = messages_by_period.get('older', [])

    # Build the temporal prompt sections
    sections = []
    if last_24h:
        sections.append("[LAST 24H]\n" + "\n".join(last_24h))
    if older:
        sections.append("[OLDER 24-48H]\n" + "\n".join(older))

    user_input = "\n\n".join(sections) if sections else "(no messages)"

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user",   "content": user_input},
        ]
    )

    content = response.choices[0].message.content.strip()
    usage   = getattr(response, 'usage', None)

    logger.info(
        'classifier_response',
        extra={
            'event':            'classifier_response',
            'classifier_model': settings.OPENAI_MODEL,
            'user_input':       user_input,
            'output':           content,
            'usage':            str(usage),
        }
    )

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error(
            'classifier_invalid_json',
            extra={'event': 'classifier_invalid_json', 'output': content}
        )
        raise
