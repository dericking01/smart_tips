import unicodedata

BANNED_TERMS = [
    "dawa",
    "umeugua",
    "tumia vidonge",
    "guaranteed cure",
    "stop medication",
    "emergency treatment",
    "take medicine",
    "take pills",
    "prescribe",
    "pill",
    "tablet",
    "injection",
    "hospital",
    "diagnosed",
    "you have",
    "cure",
    "treatment"
]

MARKDOWN_MARKERS = ['*', '_', '~', '`', '#', '[', ']', '>']


def _contains_emoji(text):
    for char in text:
        if ord(char) > 10000:
            category = unicodedata.name(char, '')
            if 'EMOJI' in category or 'FACE' in category or 'HEART' in category:
                return True
    return False


def validate_safety(message):
    if not isinstance(message, str) or not message.strip():
        return False, 'empty_message'

    lower = message.lower()
    for term in BANNED_TERMS:
        if term in lower:
            return False, f'banned_term:{term}'

    if any(marker in message for marker in MARKDOWN_MARKERS):
        return False, 'markdown_present'

    if _contains_emoji(message):
        return False, 'emoji_present'

    return True, None