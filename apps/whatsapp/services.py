import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.complaints.models import ComplaintAssignment

from .client import WhatsAppAPIError, send_template_message
from .models import WhatsAppNotification
from .phone import InvalidWhatsAppNumber, normalize_whatsapp_number

logger = logging.getLogger('apps.whatsapp')

MAX_ATTEMPTS = 3
RETRY_DELAYS_MINUTES = (1, 5, 15)


def _issue_summary(complaint):
    names = list(complaint.issues.values_list('name', flat=True))
    if names:
        summary = ', '.join(names)
    else:
        summary = complaint.others_description or 'Hardware issue'
    return summary.strip()[:500]


def _build_components(notification):
    complaint = notification.complaint
    body_parameters = [
        {'type': 'text', 'text': notification.engineer.full_name[:120]},
        {'type': 'text', 'text': complaint.reference},
        {'type': 'text', 'text': complaint.zone.name if complaint.zone else 'Unassigned'},
        {'type': 'text', 'text': _issue_summary(complaint)},
    ]
    return [
        {'type': 'body', 'parameters': body_parameters},
        {
            'type': 'button',
            'sub_type': 'url',
            'index': '0',
            'parameters': [{'type': 'text', 'text': str(complaint.id)}],
        },
    ]


def _mark_skipped(notification, reason):
    notification.status = WhatsAppNotification.STATUS_SKIPPED
    notification.last_error = reason[:2000]
    notification.next_attempt_at = None
    notification.save(
        update_fields=['status', 'last_error', 'next_attempt_at']
    )
    logger.info(
        '[WHATSAPP] Skipped assignment notification #%s | %s',
        notification.pk,
        reason,
    )
    return notification


def enqueue_assignment_notification(assignment_id):
    assignment = (
        ComplaintAssignment.objects
        .select_related(
            'complaint', 'complaint__zone', 'engineer', 'assigned_by',
        )
        .filter(pk=assignment_id, unassigned_at__isnull=True)
        .first()
    )
    if assignment is None:
        return None

    try:
        recipient_phone = normalize_whatsapp_number(assignment.engineer.phone)
    except InvalidWhatsAppNumber:
        recipient_phone = (assignment.engineer.phone or '')[:20]

    notification, created = WhatsAppNotification.objects.get_or_create(
        assignment=assignment,
        defaults={
            'complaint': assignment.complaint,
            'engineer': assignment.engineer,
            'recipient_phone': recipient_phone,
            'template_name': settings.WHATSAPP_TEMPLATE_ASSIGNED,
            'language': settings.WHATSAPP_TEMPLATE_LANGUAGE,
        },
    )
    if not created:
        return notification

    notification.payload = {
        'to': notification.recipient_phone,
        'template': notification.template_name,
        'language': notification.language,
        'components': _build_components(notification),
    }
    notification.save(update_fields=['payload'])

    if not settings.WHATSAPP_SEND_SYNC:
        return notification

    try:
        return send_assignment_notification(notification.pk)
    except Exception:
        logger.exception(
            '[WHATSAPP] Unexpected send failure for notification #%s',
            notification.pk,
        )
        return notification


def send_assignment_notification(notification_id):
    notification = (
        WhatsAppNotification.objects
        .select_related('complaint', 'complaint__zone', 'engineer')
        .filter(pk=notification_id)
        .first()
    )
    if notification is None:
        return None

    if notification.status in {
        WhatsAppNotification.STATUS_SENT,
        WhatsAppNotification.STATUS_DELIVERED,
        WhatsAppNotification.STATUS_READ,
    }:
        return notification

    if not settings.WHATSAPP_ENABLED:
        return _mark_skipped(notification, 'WhatsApp notifications are disabled.')

    if not notification.engineer.whatsapp_opt_in:
        return _mark_skipped(notification, 'Engineer has not opted in to WhatsApp.')

    try:
        recipient_phone = normalize_whatsapp_number(notification.engineer.phone)
    except InvalidWhatsAppNumber as exc:
        return _mark_skipped(notification, str(exc))

    if notification.recipient_phone != recipient_phone:
        notification.recipient_phone = recipient_phone
        notification.save(update_fields=['recipient_phone'])

    if notification.attempts >= MAX_ATTEMPTS:
        notification.status = WhatsAppNotification.STATUS_FAILED
        notification.failed_at = timezone.now()
        notification.last_error = notification.last_error or 'Maximum attempts reached.'
        notification.save(
            update_fields=['status', 'failed_at', 'last_error']
        )
        return notification

    notification.status = WhatsAppNotification.STATUS_SENDING
    notification.attempts += 1
    notification.last_attempt_at = timezone.now()
    notification.save(
        update_fields=['status', 'attempts', 'last_attempt_at']
    )

    try:
        response = send_template_message(
            to=recipient_phone,
            template_name=notification.template_name,
            language=notification.language,
            components=_build_components(notification),
        )
        messages = response.get('messages') or []
        wamid = messages[0].get('id') if messages else None
        if not wamid:
            raise WhatsAppAPIError('WhatsApp did not return a message id.')
        notification.mark_sent(wamid)
        logger.info(
            '[WHATSAPP] Sent assignment notification #%s | complaint=#%s | to=%s',
            notification.pk,
            notification.complaint_id,
            recipient_phone[-4:],
        )
    except WhatsAppAPIError as exc:
        delay_index = min(notification.attempts - 1, len(RETRY_DELAYS_MINUTES) - 1)
        retry_at = (
            timezone.now() + timedelta(minutes=RETRY_DELAYS_MINUTES[delay_index])
            if exc.retryable and notification.attempts < MAX_ATTEMPTS
            else None
        )
        notification.mark_failed(str(exc), retry_at=retry_at)
        logger.warning(
            '[WHATSAPP] Delivery failed for notification #%s | retry_at=%s | %s',
            notification.pk,
            retry_at,
            exc,
        )
    except Exception as exc:
        notification.mark_failed(str(exc))
        logger.exception(
            '[WHATSAPP] Unexpected error for notification #%s',
            notification.pk,
        )

    return notification
