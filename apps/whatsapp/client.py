import logging

import httpx
from django.conf import settings

logger = logging.getLogger('apps.whatsapp')

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class WhatsAppAPIError(Exception):
    def __init__(self, message, *, status_code=None, retryable=False, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.response = response or {}


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        return response.text[:1000] or f'HTTP {response.status_code}'

    error = data.get('error') if isinstance(data, dict) else None
    if isinstance(error, dict):
        return error.get('message') or error.get('error_user_msg') or str(error)
    return str(error or data)[:1000]


def send_template_message(to, template_name, language, components):
    if not settings.WHATSAPP_ENABLED:
        raise WhatsAppAPIError('WhatsApp notifications are disabled.')
    if not settings.WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppAPIError('WHATSAPP_ACCESS_TOKEN is not configured.')
    if not settings.WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppAPIError('WHATSAPP_PHONE_ID is not configured.')

    url = (
        f'https://graph.facebook.com/{settings.WHATSAPP_GRAPH_VERSION}/'
        f'{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
    )
    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': language},
            'components': components,
        },
    }

    try:
        with httpx.Client(timeout=settings.WHATSAPP_REQUEST_TIMEOUT) as client:
            response = client.post(
                url,
                headers={
                    'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
                    'Content-Type': 'application/json',
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise WhatsAppAPIError(
            f'WhatsApp request failed: {exc}',
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        message = _error_message(response)
        logger.warning(
            '[WHATSAPP] Send failed | status=%s | to=%s | %s',
            response.status_code,
            to[-4:],
            message,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise WhatsAppAPIError(
            message,
            status_code=response.status_code,
            retryable=response.status_code in RETRYABLE_STATUS_CODES,
            response=body,
        )

    return response.json()
