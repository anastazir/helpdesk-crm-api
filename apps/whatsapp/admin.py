from django.contrib import admin

from .models import (
    WhatsAppNotification,
    WhatsAppSettings,
    WhatsAppWebhookEvent,
)


@admin.register(WhatsAppNotification)
class WhatsAppNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'complaint', 'engineer', 'status', 'attempts',
        'recipient_phone', 'queued_at', 'sent_at',
    )
    list_filter = ('status', 'template_name', 'language')
    search_fields = (
        'complaint__reference', 'engineer__full_name',
        'engineer__email', 'wamid',
    )
    readonly_fields = (
        'assignment', 'complaint', 'engineer', 'recipient_phone',
        'template_name', 'language', 'status', 'wamid', 'payload',
        'attempts', 'last_error', 'queued_at', 'last_attempt_at',
        'next_attempt_at', 'sent_at', 'delivered_at', 'read_at',
        'failed_at',
    )


@admin.register(WhatsAppWebhookEvent)
class WhatsAppWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_key', 'received_at', 'processed_at')
    readonly_fields = (
        'event_key', 'payload', 'received_at', 'processed_at',
        'processing_error',
    )


@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'use_whatsapp', 'updated_by', 'updated_at')
    readonly_fields = ('updated_by', 'updated_at')
