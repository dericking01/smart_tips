MIN_LENGTH = 100
MAX_LENGTH = 155


def validate_length(message):
    if not isinstance(message, str) or not message.strip():
        return False, 'empty_message'

    length = len(message.strip())

    if length < MIN_LENGTH:
        return False, f'too_short:{length}'

    if length > MAX_LENGTH:
        return False, f'too_long:{length}'

    return True, None