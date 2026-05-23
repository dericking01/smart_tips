import json
from openai import OpenAI
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
    return json.loads(content)