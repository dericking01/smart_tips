BANNED_TERMS = [
    "dawa",
    "umeugua",
    "tumia vidonge",
    "guaranteed cure"
]

def validate_safety(message):
    lower = message.lower()

    for term in BANNED_TERMS:
        if term in lower:
            return False

    return True