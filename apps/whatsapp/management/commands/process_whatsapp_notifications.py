from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.whatsapp.models import WhatsAppNotification
from apps.whatsapp.services import send_assignment_notification


class Command(BaseCommand):
    help = 'Send queued WhatsApp assignment notifications.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)
        parser.add_argument('--id', type=int, default=None)
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Reset failed notifications and attempt them again.',
        )

    def handle(self, *args, **options):
        if options['id']:
            queryset = WhatsAppNotification.objects.filter(pk=options['id'])
            if options['retry_failed']:
                queryset.update(
                    status=WhatsAppNotification.STATUS_QUEUED,
                    attempts=0,
                    failed_at=None,
                    next_attempt_at=None,
                )
        else:
            if options['retry_failed']:
                WhatsAppNotification.objects.filter(
                    status=WhatsAppNotification.STATUS_FAILED
                ).update(
                    status=WhatsAppNotification.STATUS_QUEUED,
                    attempts=0,
                    failed_at=None,
                    next_attempt_at=None,
                )
            now = timezone.now()
            queryset = WhatsAppNotification.objects.filter(
                status=WhatsAppNotification.STATUS_QUEUED
            ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))

        sent = failed = skipped = 0
        for notification in queryset.order_by('queued_at')[:options['limit']]:
            result = send_assignment_notification(notification.pk)
            if result is None:
                continue
            if result.status in {
                WhatsAppNotification.STATUS_SENT,
                WhatsAppNotification.STATUS_DELIVERED,
                WhatsAppNotification.STATUS_READ,
            }:
                sent += 1
            elif result.status == WhatsAppNotification.STATUS_SKIPPED:
                skipped += 1
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'WhatsApp notifications: sent={sent} failed={failed} skipped={skipped}'
            )
        )
