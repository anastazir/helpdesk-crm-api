from django.conf import settings
from django.db import models
from django.utils import timezone


class WhatsAppNotification(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_READ = 'read'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'

    STATUS_CHOICES = [
        (STATUS_QUEUED, 'Queued'),
        (STATUS_SENDING, 'Sending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_READ, 'Read'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    assignment = models.OneToOneField(
        'complaints.ComplaintAssignment',
        on_delete=models.CASCADE,
        related_name='whatsapp_notification',
    )
    complaint = models.ForeignKey(
        'complaints.Complaint',
        on_delete=models.CASCADE,
        related_name='whatsapp_notifications',
    )
    engineer = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='whatsapp_notifications',
    )
    recipient_phone = models.CharField(max_length=20)
    template_name = models.CharField(max_length=255)
    language = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
    )
    wamid = models.CharField(max_length=255, unique=True, null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'whatsapp_notifications'
        ordering = ['-queued_at']

    def mark_sent(self, wamid):
        self.wamid = wamid
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()
        self.last_error = ''
        self.next_attempt_at = None
        self.save(
            update_fields=[
                'wamid', 'status', 'sent_at', 'last_error',
                'next_attempt_at',
            ]
        )

    def mark_failed(self, message, retry_at=None):
        self.status = (
            self.STATUS_QUEUED if retry_at is not None else self.STATUS_FAILED
        )
        self.last_error = (message or '')[:2000]
        self.next_attempt_at = retry_at
        if retry_at is None:
            self.failed_at = timezone.now()
        self.save(
            update_fields=[
                'status', 'last_error', 'next_attempt_at', 'failed_at',
            ]
        )

    def __str__(self):
        return f'WhatsApp {self.status} for complaint #{self.complaint_id}'


class WhatsAppWebhookEvent(models.Model):
    event_key = models.CharField(max_length=64, unique=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'whatsapp_webhook_events'
        ordering = ['-received_at']

    def __str__(self):
        return self.event_key


class WhatsAppSettings(models.Model):
    use_whatsapp = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'whatsapp_settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f'Use WhatsApp: {self.use_whatsapp}'


def whatsapp_configured():
    return bool(
        settings.WHATSAPP_ACCESS_TOKEN
        and settings.WHATSAPP_PHONE_NUMBER_ID
    )


def whatsapp_feature_enabled():
    if not settings.USE_WHATSAPP:
        return False
    if not settings.WHATSAPP_ENABLED:
        return False
    return WhatsAppSettings.load().use_whatsapp
