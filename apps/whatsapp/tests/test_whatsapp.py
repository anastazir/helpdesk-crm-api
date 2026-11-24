import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status

from apps.complaints.models import ComplaintAssignment
from apps.users.models import User
from apps.whatsapp.models import WhatsAppNotification, WhatsAppWebhookEvent
from apps.whatsapp.phone import InvalidWhatsAppNumber, normalize_whatsapp_number
from core.tests.base import BaseAPITest


class WhatsAppPhoneTest(TestCase):
    def test_normalizes_indian_numbers(self):
        self.assertEqual(normalize_whatsapp_number('9000000004'), '919000000004')
        self.assertEqual(normalize_whatsapp_number('+91 90000 00004'), '919000000004')
        self.assertEqual(normalize_whatsapp_number('0919000000004'), '919000000004')
        self.assertEqual(normalize_whatsapp_number('0091 9000000004'), '919000000004')

    def test_rejects_empty_number(self):
        with self.assertRaises(InvalidWhatsAppNumber):
            normalize_whatsapp_number('')


@override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_APP_SECRET='test-app-secret',
    WHATSAPP_VERIFY_TOKEN='test-verify-token',
    WHATSAPP_TEMPLATE_ASSIGNED='complaint_assigned_engineer',
    WHATSAPP_TEMPLATE_LANGUAGE='en_US',
    WHATSAPP_SEND_SYNC=True,
)
class AssignmentNotificationTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.engineer.whatsapp_opt_in = True
        self.engineer.whatsapp_opt_in_at = self.engineer.created_at
        self.engineer.whatsapp_opt_in_source = 'admin_form'
        self.engineer.save(
            update_fields=[
                'whatsapp_opt_in', 'whatsapp_opt_in_at',
                'whatsapp_opt_in_source',
            ]
        )
        self.complaint = self.make_complaint()
        self._wamid_counter = 0

    def assign(self, engineer=None):
        self._wamid_counter += 1
        wamid = f'wamid.test-{self._wamid_counter}'
        self.auth_as(self.supervisor)
        with patch(
            'apps.whatsapp.services.send_template_message',
            return_value={'messages': [{'id': wamid}]},
        ) as sender:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f'/api/complaints/{self.complaint.id}/assign/',
                    {'engineer_id': (engineer or self.engineer).id},
                    format='json',
                )
        return response, sender

    def test_assignment_creates_and_sends_notification(self):
        response, sender = self.assign()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = WhatsAppNotification.objects.get(
            assignment__complaint=self.complaint,
            assignment__engineer=self.engineer,
        )
        self.assertEqual(notification.status, WhatsAppNotification.STATUS_SENT)
        self.assertEqual(notification.wamid, 'wamid.test-1')
        self.assertEqual(notification.recipient_phone, '919000000004')
        self.assertEqual(notification.template_name, 'complaint_assigned_engineer')
        sender.assert_called_once()

    def test_reassignment_notifies_new_engineer(self):
        self.assign()
        other = User.objects.create_user(
            email='other-wa@test.com',
            password='Eng@123',
            full_name='Other WhatsApp Engineer',
            role='engineer',
            phone='9876543210',
            whatsapp_opt_in=True,
        )
        response, _ = self.assign(other)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications = WhatsAppNotification.objects.filter(
            assignment__complaint=self.complaint
        )
        self.assertEqual(notifications.count(), 2)
        self.assertTrue(notifications.filter(engineer=other).exists())

    def test_same_engineer_does_not_send_duplicate(self):
        self.assign()
        self.assign()
        self.assertEqual(
            WhatsAppNotification.objects.filter(
                assignment__complaint=self.complaint
            ).count(),
            1,
        )

    def test_no_opt_in_skips_send(self):
        self.engineer.whatsapp_opt_in = False
        self.engineer.save(update_fields=['whatsapp_opt_in'])
        response, sender = self.assign()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = WhatsAppNotification.objects.get(
            assignment__complaint=self.complaint
        )
        self.assertEqual(notification.status, WhatsAppNotification.STATUS_SKIPPED)
        self.assertIn('opted in', notification.last_error)
        sender.assert_not_called()


@override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_APP_SECRET='test-app-secret',
    WHATSAPP_VERIFY_TOKEN='test-verify-token',
)
class WhatsAppWebhookTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.engineer.whatsapp_opt_in = True
        self.engineer.save(update_fields=['whatsapp_opt_in'])
        self.complaint = self.make_complaint()
        self.assignment = ComplaintAssignment.objects.create(
            complaint=self.complaint,
            engineer=self.engineer,
            assigned_by=self.supervisor,
        )
        self.notification = WhatsAppNotification.objects.create(
            assignment=self.assignment,
            complaint=self.complaint,
            engineer=self.engineer,
            recipient_phone='919000000004',
            template_name='complaint_assigned_engineer',
            language='en_US',
            status=WhatsAppNotification.STATUS_SENT,
            wamid='wamid.webhook-1',
        )

    def post_webhook(self, payload, signature=None):
        raw = json.dumps(payload).encode()
        if signature is None:
            signature = 'sha256=' + hmac.new(
                b'test-app-secret', raw, hashlib.sha256
            ).hexdigest()
        return self.client.post(
            '/api/webhooks/whatsapp/',
            data=raw,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    def test_verification_challenge(self):
        response = self.client.get(
            '/api/webhooks/whatsapp/',
            {
                'hub.mode': 'subscribe',
                'hub.verify_token': 'test-verify-token',
                'hub.challenge': 'challenge-123',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'challenge-123')

    def test_delivery_status_updates_notification(self):
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'statuses': [{
                            'id': 'wamid.webhook-1',
                            'status': 'delivered',
                            'timestamp': '1700000000',
                            'recipient_id': '919000000004',
                        }],
                    },
                }],
            }],
        }
        response = self.post_webhook(payload)
        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, 'delivered')
        self.assertIsNotNone(self.notification.delivered_at)
        self.assertTrue(WhatsAppWebhookEvent.objects.exists())

    def test_duplicate_webhook_is_idempotent(self):
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'statuses': [{
                            'id': 'wamid.webhook-1',
                            'status': 'delivered',
                        }],
                    },
                }],
            }],
        }
        self.assertEqual(self.post_webhook(payload).status_code, 200)
        self.assertEqual(self.post_webhook(payload).status_code, 200)
        self.assertEqual(WhatsAppWebhookEvent.objects.count(), 1)

    def test_invalid_signature_is_rejected(self):
        response = self.post_webhook(
            {'object': 'whatsapp_business_account', 'entry': []},
            signature='sha256=bad',
        )
        self.assertEqual(response.status_code, 403)

    def test_stop_reply_opts_out(self):
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '919000000004',
                            'id': 'wamid.inbound-1',
                            'type': 'text',
                            'text': {'body': 'STOP'},
                        }],
                    },
                }],
            }],
        }
        response = self.post_webhook(payload)
        self.assertEqual(response.status_code, 200)
        self.engineer.refresh_from_db()
        self.assertFalse(self.engineer.whatsapp_opt_in)
        self.assertIsNotNone(self.engineer.whatsapp_opt_out_at)

    def test_start_reply_opts_in(self):
        self.engineer.whatsapp_opt_in = False
        self.engineer.save(update_fields=['whatsapp_opt_in'])
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': '919000000004',
                            'id': 'wamid.inbound-2',
                            'type': 'text',
                            'text': {'body': 'START'},
                        }],
                    },
                }],
            }],
        }
        response = self.post_webhook(payload)
        self.assertEqual(response.status_code, 200)
        self.engineer.refresh_from_db()
        self.assertTrue(self.engineer.whatsapp_opt_in)
        self.assertIsNotNone(self.engineer.whatsapp_opt_in_at)
