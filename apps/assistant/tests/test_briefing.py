from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.complaints.models import Complaint, ComplaintAssignment, StatusHistory
from apps.users.models import User
from apps.zones.models import Zone

from ..services import (
    BriefingConfigurationError,
    BriefingUpstreamError,
    build_briefing_context,
)


class AssistantBriefingTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email='ai-admin@example.com',
            password='test-pass',
            full_name='AI Admin',
            phone='1000000000',
            role='admin',
        )
        self.helpdesk = User.objects.create_user(
            email='ai-helpdesk@example.com',
            password='test-pass',
            full_name='AI Help Desk',
            phone='1000000001',
            role='helpdesk',
        )
        self.engineer = User.objects.create_user(
            email='ai-engineer@example.com',
            password='test-pass',
            full_name='AI Engineer',
            phone='1000000002',
            role='engineer',
        )
        self.zone = Zone.objects.create(
            name='AI Test Zone',
            created_by=self.admin,
        )
        self.complaint = Complaint.objects.create(
            caller_phone='9999999999',
            caller_name='Sensitive Caller',
            zone=self.zone,
            created_by=self.admin,
        )
        ComplaintAssignment.objects.create(
            complaint=self.complaint,
            engineer=self.engineer,
            assigned_by=self.admin,
        )
        StatusHistory.objects.create(
            complaint=self.complaint,
            previous_status='open',
            new_status='resolved',
            changed_by=self.engineer,
        )
        Complaint.objects.filter(pk=self.complaint.pk).update(status='resolved')

    def test_context_is_aggregated_and_has_no_caller_pii(self):
        context = build_briefing_context()

        self.assertEqual(context['new_today'], 1)
        self.assertEqual(context['resolved_today'], 1)
        self.assertEqual(context['closed_today'], 0)
        self.assertEqual(context['open_unassigned'], 0)
        self.assertEqual(context['active_total'], 1)
        self.assertEqual(context['top_zones_today'][0]['zone'], 'AI Test Zone')
        self.assertEqual(context['engineer_workload'][0]['engineer'], 'AI Engineer')
        self.assertNotIn('caller_phone', context)
        self.assertNotIn('caller_name', context)
        self.assertNotIn('aadhaar', context)

    def test_requires_authentication(self):
        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_engineer_is_forbidden(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.assistant.views.generate_briefing')
    def test_admin_receives_briefing(self, generate):
        generate.return_value = {
            'briefing': 'Headline: One resolved complaint today.',
            'generated_at': '2026-11-22T10:00:00+05:30',
            'as_of': '2026-11-22T10:00:00+05:30',
            'timezone': 'Asia/Kolkata',
            'model': 'deepseek/deepseek-v4.1-flash-1017',
            'provider': 'Test Provider',
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'total_tokens': 150,
                'cost': 0.0001,
            },
            'latency_ms': 1200,
        }
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(
            response.data['data']['briefing'],
            'Headline: One resolved complaint today.',
        )
        self.assertEqual(response.data['data']['usage']['total_tokens'], 150)
        generate.assert_called_once()

    @patch('apps.assistant.views.generate_briefing')
    def test_admin_receives_briefing(self, generate):
        generate.return_value = {
            'briefing': 'Briefing',
            'generated_at': '2026-11-22T10:00:00+05:30',
            'as_of': '2026-11-22T10:00:00+05:30',
            'timezone': 'Asia/Kolkata',
            'model': 'deepseek/deepseek-v4.1-flash-1017',
            'provider': 'Test Provider',
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 50,
                'total_tokens': 150,
                'cost': 0.0001,
            },
            'latency_ms': 1200,
        }
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.assistant.views.generate_briefing')
    def test_configuration_error_is_safe(self, generate):
        generate.side_effect = BriefingConfigurationError('Not configured')
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertFalse(response.data['success'])

    @patch('apps.assistant.views.generate_briefing')
    def test_upstream_error_is_safe(self, generate):
        generate.side_effect = BriefingUpstreamError('Provider unavailable')
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse('assistant-briefing'))

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['message'], 'Provider unavailable')
