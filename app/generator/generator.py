from openai import OpenAI
from app.config.settings import settings
from app.generator.prompts import GENERATOR_PROMPT

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def generate_sms(profile):
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.5,
        messages=[
            {
                "role": "system",
                "content": GENERATOR_PROMPT
            },
            {
                "role": "user",
                "content": str(profile)
            }
        ]
    )

    return response.choices[0].message.content.strip()