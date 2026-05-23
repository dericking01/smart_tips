import json
from openai import OpenAI
from app.config.logger import logger
from app.config.settings import settings
from app.classifier.prompts import CLASSIFIER_PROMPT

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def classify_topics(messages):
    joined = "\n".join(messages)

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": CLASSIFIER_PROMPT
            },
            {
                "role": "user",
                "content": joined
            }
        ]
    )

    content = response.choices[0].message.content
    usage = getattr(response, 'usage', None)
    logger.info(
        'classifier_response',
        extra={
            'event': 'classifier_response',
            'classifier_model': settings.OPENAI_MODEL,
            'prompt': CLASSIFIER_PROMPT.strip(),
            'user_input': joined,
            'output': content,
            'usage': usage
        }
    )

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error(
            'classifier_invalid_json',
            extra={
                'event': 'classifier_invalid_json',
                'output': content
            }
        )
        raise