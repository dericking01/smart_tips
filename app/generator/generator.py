import json

from openai import OpenAI

from app.config.logger import logger
from app.config.settings import settings
from app.generator.prompts import BATCH_TIPS_PROMPT, GENERATOR_PROMPT

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_sms(profile: dict) -> str:
    """Generate a single personalised SMS tip for a subscriber.

    Args:
        profile: {"language": "sw"|"en", "topics": ["primary_topic", ...]}
                 Topics are ordered highest-priority first.

    Returns:
        The generated SMS text (stripped).
    """
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.5,
        messages=[
            {"role": "system", "content": GENERATOR_PROMPT},
            {"role": "user",   "content": json.dumps(profile)},   # proper JSON, not str()
        ]
    )

    content = response.choices[0].message.content.strip()
    usage   = getattr(response, 'usage', None)

    logger.info(
        'generator_response',
        extra={
            'event':           'generator_response',
            'generator_model': settings.OPENAI_MODEL,
            'profile':         profile,
            'output':          content,
            'usage':           str(usage),
        }
    )

    return content


def generate_tips_batch(count: int = 10, language: str = 'sw') -> list:
    """Make a single OpenAI call and return a list of `count` generic health tips."""
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.9,   # higher temp = more variety across tips
        messages=[
            {"role": "system", "content": BATCH_TIPS_PROMPT},
            {"role": "user",   "content": json.dumps({"count": count, "language": language})},
        ]
    )

    content = response.choices[0].message.content.strip()
    usage   = getattr(response, 'usage', None)

    logger.info(
        'batch_tips_generated',
        extra={
            'event':           'batch_tips_generated',
            'generator_model': settings.OPENAI_MODEL,
            'language':        language,
            'requested_count': count,
            'output':          content,
            'usage':           str(usage),
        }
    )

    tips = json.loads(content)

    if not isinstance(tips, list):
        raise ValueError(f"Expected a JSON array, got: {type(tips).__name__}")

    return [t.strip() for t in tips if isinstance(t, str) and t.strip()]
