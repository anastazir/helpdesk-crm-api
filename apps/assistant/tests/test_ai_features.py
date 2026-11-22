from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assistant.tools import execute_tool
from apps.complaints.models import (
    Complaint,
    ComplaintAssignment,
    IssueType,
)
from apps.users.models import User
from apps.zones.models import Zone


def result_meta():
    return {
        'generated_at': '2026-11-22T10:00:00+05:30',
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


class AssistantFeatureAPITest(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email='feature-admin@example.com',
            password='test-pass',
            full_name='Feature Admin',
            phone='1000000100',
            role='admin',
        )
        self.helpdesk = User.objects.create_user(
            email='feature-helpdesk@example.com',
            password='test-pass',
            full_name='Feature Help Desk',
            phone='1000000101',
            role='helpdesk',
        )
        self.engineer = User.objects.create_user(
            email='feature-engineer@example.com',
            password='test-pass',
            full_name='Feature Engineer',
            phone='1000000102',
            role='engineer',
        )
        self.other_engineer = User.objects.create_user(
            email='feature-other@example.com',
            password='test-pass',
            full_name='Other Engineer',
            phone='1000000103',
            role='engineer',
        )
        self.zone = Zone.objects.create(
            name='Feature Zone',
            created_by=self.admin,
        )
        self.issue = IssueType.objects.create(
            name='Printer',
            order=1,
            is_active=True,
        )
        self.complaint = Complaint.objects.create(
            caller_phone='9999999999',
            caller_name='Private Caller',
            aadhaar='123412341234',
            address='Private Address',
            zone=self.zone,
            created_by=self.admin,
        )
        self.complaint.issues.add(self.issue)
        self.assignment = ComplaintAssignment.objects.create(
            complaint=self.complaint,
            engineer=self.engineer,
            assigned_by=self.admin,
        )

    def test_tools_hide_complaint_from_unassigned_engineer(self):
        result = execute_tool(
            self.other_engineer,
            'get_complaint',
            {'complaint_id': self.complaint.id},
        )

        self.assertIn('error', result)

    def test_tools_return_no_caller_pii_to_assigned_engineer(self):
        result = execute_tool(
            self.engineer,
            'get_complaint',
            {'complaint_id': self.complaint.id},
        )

        complaint = result['complaint']
        self.assertEqual(complaint['id'], self.complaint.id)
        self.assertNotIn('caller_phone', complaint)
        self.assertNotIn('caller_name', complaint)
        self.assertNotIn('aadhaar', complaint)
        self.assertNotIn('address', complaint)

    def test_engineer_cannot_use_operations_summary_tool(self):
        result = execute_tool(self.engineer, 'get_operations_summary', {})

        self.assertIn('error', result)

    @patch('apps.assistant.views.chat_with_tools')
    def test_chat_endpoint_allows_admin(self, chat):
        chat.return_value = {
            'reply': 'Two complaints are at risk.',
            'references': [{'id': self.complaint.id, 'label': '#100001'}],
            'tools_used': ['get_sla_risks'],
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse('assistant-chat'),
            {
                'message': 'What is at risk?',
                'history': [],
                'language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['reply'], 'Two complaints are at risk.')
        self.assertEqual(response.data['data']['tools_used'], ['get_sla_risks'])

    @patch('apps.assistant.views.chat_with_tools')
    def test_chat_endpoint_allows_engineer(self, chat):
        chat.return_value = {
            'reply': 'Your plan is ready.',
            'references': [],
            'tools_used': [],
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.engineer)

        response = self.client.post(
            reverse('assistant-chat'),
            {'message': 'Plan my day', 'language': 'en'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_chat_rejects_empty_message(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse('assistant-chat'),
            {'message': '', 'language': 'en'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.assistant.views.generate_complaint_copilot')
    def test_complaint_copilot_requires_access(self, copilot):
        copilot.return_value = {
            'text': 'Summary',
            'task': 'summary',
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.other_engineer)

        response = self.client.post(
            reverse('assistant-complaint-copilot'),
            {
                'complaint_id': self.complaint.id,
                'task': 'summary',
                'language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.assistant.views.generate_complaint_copilot')
    def test_complaint_copilot_allows_assigned_engineer(self, copilot):
        copilot.return_value = {
            'text': 'Summary',
            'task': 'summary',
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.engineer)

        response = self.client.post(
            reverse('assistant-complaint-copilot'),
            {
                'complaint_id': self.complaint.id,
                'task': 'summary',
                'language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.assistant.views.generate_engineer_plan')
    def test_engineer_plan_is_engineer_only(self, plan):
        plan.return_value = {
            'text': 'Start here.',
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.admin)

        forbidden = self.client.post(
            reverse('assistant-engineer-plan'),
            {'language': 'en'},
            format='json',
        )

        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.engineer)
        allowed = self.client.post(
            reverse('assistant-engineer-plan'),
            {'language': 'en'},
            format='json',
        )

        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed.data['data']['text'], 'Start here.')

    @patch('apps.assistant.views.generate_triage')
    def test_triage_maps_suggested_names_to_issue_ids(self, triage):
        triage.return_value = {
            'suggested_issues': ['Printer'],
            'urgency': 'soon',
            'reason': 'Printer is offline.',
            'next_step': 'Check the printer connection.',
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.helpdesk)

        response = self.client.post(
            reverse('assistant-triage'),
            {
                'issue_ids': [],
                'others_description': 'The printer is offline.',
                'department': 'Revenue',
                'designation': 'Clerk',
                'language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['data']['suggested_issues'],
            [{'id': self.issue.id, 'name': 'Printer'}],
        )
        self.assertEqual(response.data['data']['urgency'], 'soon')

    def test_triage_requires_symptoms(self):
        self.client.force_authenticate(self.helpdesk)

        response = self.client.post(
            reverse('assistant-triage'),
            {'issue_ids': [], 'others_description': '', 'language': 'en'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
