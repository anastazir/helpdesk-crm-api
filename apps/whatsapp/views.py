import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.users.models import User

from .models import WhatsAppNotification, WhatsAppWebhookEvent
from .phone import normalize_whatsapp_number

logger = logging.getLogger('apps.whatsapp')

STOP_WORDS = {'stop', 'unsubscribe', 'optout', 'opt out', 'cancel'}
START_WORDS = {'start', 'unstop', 'subscribe', 'optin', 'opt in', 'yes'}

STATUS_RANK = {
    WhatsAppNotification.STATUS_QUEUED: 0,
    WhatsAppNotification.STATUS_SENDING: 1,
    WhatsAppNotification.STATUS_SENT: 2,
    WhatsAppNotification.STATUS_DELIVERED: 3,
    WhatsAppNotification.STATUS_READ: 4,
}


def _valid_signature(raw_body, signature_header):
    if not signature_header or not settings.WHATSAPP_APP_SECRET:
        return False
    expected = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix('sha256=')
    return hmac.compare_digest(expected, received)


def _find_user_by_phone(phone):
    try:
        digits = normalize_whatsapp_number(phone)
    except Exception:
        return None
    return (
        User.objects
        .filter(Q(phone=digits) | Q(phone=digits[-10:]))
        .filter(is_deleted=False)
        .first()
    )


def _apply_status(status):
    wamid = status.get('id')
    state = (status.get('status') or '').lower()
    if not wamid or not state:
        return

    notification = WhatsAppNotification.objects.filter(wamid=wamid).first()
    if notification is None:
        return

    if state == 'failed':
        errors = status.get('errors') or []
        message = 'WhatsApp delivery failed.'
        if errors and isinstance(errors[0], dict):
            message = (
                errors[0].get('error_user_msg')
                or errors[0].get('message')
                or errors[0].get('title')
                or message
            )
        notification.status = WhatsAppNotification.STATUS_FAILED
        notification.failed_at = timezone.now()
        notification.last_error = str(message)[:2000]
        notification.next_attempt_at = None
        notification.save(
            update_fields=[
                'status', 'failed_at', 'last_error', 'next_attempt_at',
            ]
        )
        return

    if state not in STATUS_RANK:
        return
    if STATUS_RANK.get(notification.status, -1) > STATUS_RANK[state]:
        return

    notification.status = state
    update_fields = ['status']
    now = timezone.now()
    if state == WhatsAppNotification.STATUS_SENT and notification.sent_at is None:
        notification.sent_at = now
        update_fields.append('sent_at')
    elif state == WhatsAppNotification.STATUS_DELIVERED:
        notification.delivered_at = now
        update_fields.append('delivered_at')
    elif state == WhatsAppNotification.STATUS_READ:
        notification.read_at = now
        update_fields.append('read_at')
    notification.save(update_fields=update_fields)


def _apply_inbound_message(message):
    sender = message.get('from')
    body = ((message.get('text') or {}).get('body') or '').strip().lower()
    if not sender or not body:
        return

    user = _find_user_by_phone(sender)
    if user is None:
        return

    if body in STOP_WORDS:
        user.whatsapp_opt_in = False
        user.whatsapp_opt_out_at = timezone.now()
        user.whatsapp_opt_in_source = 'whatsapp_reply'
        user.save(
            update_fields=[
                'whatsapp_opt_in', 'whatsapp_opt_out_at',
                'whatsapp_opt_in_source',
            ]
        )
        WhatsAppNotification.objects.filter(
            engineer=user,
            status__in=[
                WhatsAppNotification.STATUS_QUEUED,
                WhatsAppNotification.STATUS_SENDING,
            ],
        ).update(
            status=WhatsAppNotification.STATUS_SKIPPED,
            last_error='Engineer replied STOP.',
            next_attempt_at=None,
        )
        logger.info('[WHATSAPP] Opt-out received for user #%s', user.pk)
    elif body in START_WORDS:
        user.whatsapp_opt_in = True
        user.whatsapp_opt_in_at = timezone.now()
        user.whatsapp_opt_out_at = None
        user.whatsapp_opt_in_source = 'whatsapp_reply'
        user.save(
            update_fields=[
                'whatsapp_opt_in', 'whatsapp_opt_in_at',
                'whatsapp_opt_out_at', 'whatsapp_opt_in_source',
            ]
        )
        logger.info('[WHATSAPP] Opt-in received for user #%s', user.pk)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webhook(request):
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge', '')
        if (
            mode == 'subscribe'
            and settings.WHATSAPP_VERIFY_TOKEN
            and token == settings.WHATSAPP_VERIFY_TOKEN
        ):
            return HttpResponse(challenge, content_type='text/plain')
        return HttpResponse('Forbidden', status=403)

    raw_body = request.body
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not settings.WHATSAPP_APP_SECRET:
        logger.error('[WHATSAPP] Webhook rejected: WHATSAPP_APP_SECRET is not set.')
        return JsonResponse(
            {'error': 'WhatsApp webhook is not configured.'},
            status=503,
        )
    if not _valid_signature(raw_body, signature):
        return JsonResponse({'error': 'Invalid signature.'}, status=403)

    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    event_key = hashlib.sha256(raw_body).hexdigest()
    event, created = WhatsAppWebhookEvent.objects.get_or_create(
        event_key=event_key,
        defaults={'payload': payload},
    )
    if not created and event.processed_at is not None:
        return JsonResponse({'status': 'ok'})

    try:
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value') or {}
                for status in value.get('statuses', []):
                    _apply_status(status)
                for message in value.get('messages', []):
                    _apply_inbound_message(message)
        event.processed_at = timezone.now()
        event.processing_error = ''
        event.save(update_fields=['processed_at', 'processing_error'])
    except Exception as exc:
        event.processing_error = str(exc)[:2000]
        event.save(update_fields=['processing_error'])
        logger.exception('[WHATSAPP] Webhook processing failed')

    return JsonResponse({'status': 'ok'})
