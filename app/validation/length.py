def validate_length(message):
    if not isinstance(message, str) or not message.strip():
        return False, 'empty_message'

    length = len(message.strip())
    if length > 155:
        return False, 'too_long'

    return True, None