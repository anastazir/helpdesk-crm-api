import re


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw):
    if raw is None:
        raise InvalidPhoneError('Phone number is required.')
    value = re.sub(r'[\s\-()]', '', str(raw))
    if value.startswith('+91'):
        value = value[3:]
    elif len(value) == 12 and value.startswith('91'):
        value = value[2:]
    if not value.isdigit() or len(value) != 10:
        raise InvalidPhoneError('Enter a valid 10-digit Indian mobile number.')
    return value
