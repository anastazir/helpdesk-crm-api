import re

from django.conf import settings


class InvalidWhatsAppNumber(ValueError):
    pass


def normalize_whatsapp_number(value, country_code=None):
    country_code = str(
        country_code or settings.WHATSAPP_DEFAULT_COUNTRY_CODE
    ).strip().lstrip('+')
    digits = re.sub(r'\D', '', str(value or ''))
    if not digits:
        raise InvalidWhatsAppNumber('A WhatsApp phone number is required.')

    if digits.startswith('00'):
        digits = digits[2:]
    digits = digits.lstrip('0')
    if len(digits) == 10:
        digits = f'{country_code}{digits}'

    if not 10 <= len(digits) <= 15:
        raise InvalidWhatsAppNumber('Enter a valid phone number with country code.')
    return digits
