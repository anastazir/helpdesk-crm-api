from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assistant.analytics import AnalyticsValidationError, validate_analytics_sql
from apps.assistant.models import AIRequestLog
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


    @patch('apps.assistant.views.generate_export_summary')
    def test_export_summary_is_admin_only(self, summary):
        summary.return_value = {
            'text': 'Overview: 25 complaints.',
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.helpdesk)
        forbidden = self.client.post(
            reverse('assistant-export-summary'),
            {'filters': {}, 'deduplicate': False, 'language': 'en'},
            format='json',
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        allowed = self.client.post(
            reverse('assistant-export-summary'),
            {'filters': {}, 'deduplicate': False, 'language': 'en'},
            format='json',
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed.data['data']['text'], 'Overview: 25 complaints.')

    @patch('apps.assistant.views.generate_complaint_autofill')
    def test_autofill_maps_issue_and_zone(self, autofill):
        autofill.return_value = {
            'fields': {
                'caller_name': 'Ramesh',
                'caller_phone': None,
                'zone': 'Feature Zone',
                'department': 'Revenue',
                'designation': None,
                'address': None,
                'pincode': None,
                'cpu_serial': 'CPU-1',
                'monitor_serial': None,
                'issue_names': ['Printer'],
                'others_description': None,
                'notes': None,
            },
            'language': 'en',
            **result_meta(),
        }
        self.client.force_authenticate(self.helpdesk)

        response = self.client.post(
            reverse('assistant-complaint-autofill'),
            {
                'transcript': 'Ramesh, phone 98765 43210, printer issue, Feature Zone',
                'language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['data']['suggested_issue_ids'],
            [self.issue.id],
        )
        self.assertEqual(response.data['data']['zone_id'], self.zone.id)
        self.assertEqual(
            response.data['data']['fields']['caller_phone'],
            '9876543210',
        )

    def test_ai_logs_are_admin_only_and_include_inr_cost(self):
        AIRequestLog.objects.create(
            user=self.admin,
            feature='chat',
            status='success',
            request_text='What is at risk?',
            response_text='Two complaints.',
            total_tokens=120,
            cost_usd='0.00100000',
            cost_inr='0.0880',
        )
        self.client.force_authenticate(self.helpdesk)
        forbidden = self.client.get(reverse('ai-log-list'))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        listing = self.client.get(reverse('ai-log-list'))
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data['data']['results'][0]['cost_inr'], '0.0880')

        summary = self.client.get(reverse('ai-log-summary'))
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data['data']['total_requests'], 1)
        self.assertEqual(summary.data['data']['total_cost_inr'], 0.088)

        detail = self.client.get(
            reverse('ai-log-detail', args=[listing.data['data']['results'][0]['id']])
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['data']['request_text'], 'What is at risk?')


    def test_analytics_validator_blocks_writes_and_base_tables(self):
        with self.assertRaises(AnalyticsValidationError):
            validate_analytics_sql('DELETE FROM analytics_complaints')
        with self.assertRaises(AnalyticsValidationError):
            validate_analytics_sql('SELECT * FROM users')
        with self.assertRaises(AnalyticsValidationError):
            validate_analytics_sql('SELECT pg_sleep(10)')
        with self.assertRaises(AnalyticsValidationError):
            validate_analytics_sql('SELECT 1; SELECT 2')

    def test_analytics_validator_allows_case_and_boolean_logic(self):
        validated = validate_analytics_sql(
            "SELECT CASE WHEN status = 'open' AND assigned_engineer IS NOT NULL "
            "THEN 'assigned' ELSE status END AS state, COUNT(*) AS total "
            'FROM analytics_complaints GROUP BY 1'
        )
        self.assertIn('CASE', validated['sql'])

    def test_analytics_validator_allows_safe_views(self):
        validated = validate_analytics_sql(
            'SELECT status, COUNT(*) AS total '
            'FROM analytics_complaints GROUP BY status'
        )
        self.assertIn('analytics_complaints', validated['sql'])
        self.assertIn('LIMIT 1001', validated['wrapped_sql'])

    def test_sql_tool_is_admin_only(self):
        result = execute_tool(
            self.engineer,
            'run_analytics_query',
            {'sql': 'SELECT COUNT(*) AS total FROM analytics_complaints'},
        )
        self.assertIn('error', result)

    @patch('apps.assistant.views.generate_analytics_answer')
    @patch('apps.assistant.views.generate_analytics_plan')
    def test_admin_analytics_returns_chart_data(self, plan, answer):
        plan.return_value = (
            {
                'sql': (
                    'SELECT status, COUNT(*) AS total '
                    'FROM analytics_complaints GROUP BY status'
                ),
                'title': 'Complaints by status',
                'response_type': 'chart',
                'chart': {
                    'type': 'bar',
                    'x': 'status',
                    'y': 'total',
                    'series': None,
                },
                'explanation': 'Counts by status.',
            },
            {
                'model': 'deepseek/deepseek-v4.1-flash-1017',
                'provider': 'Test Provider',
                'usage': {
                    'prompt_tokens': 100,
                    'completion_tokens': 50,
                    'total_tokens': 150,
                    'cost': 0.0001,
                },
            },
            500,
        )
        answer.return_value = (
            'The largest group is assigned.',
            {
                'model': 'deepseek/deepseek-v4.1-flash-1017',
                'provider': 'Test Provider',
                'usage': {
                    'prompt_tokens': 50,
                    'completion_tokens': 20,
                    'total_tokens': 70,
                    'cost': 0.00005,
                },
            },
            300,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse('assistant-analytics'),
            {'question': 'Complaints by status', 'language': 'en'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['chart']['type'], 'bar')
        self.assertGreater(len(data['rows']), 0)
        self.assertEqual(data['chart']['x'], 'status')
        self.assertEqual(data['chart']['y'], 'total')
        self.assertIn('answer', data)

    @patch('apps.assistant.views.generate_analytics_plan')
    def test_analytics_is_admin_only(self, plan):
        plan.return_value = ({}, {}, 0)
        self.client.force_authenticate(self.helpdesk)
        response = self.client.post(
            reverse('assistant-analytics'),
            {'question': 'Complaints by status', 'language': 'en'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_tool_supports_hour_window(self):
        from django.utils import timezone
        from datetime import timedelta
        Complaint.objects.filter(pk=self.complaint.pk).update(
            created_at=timezone.now() - timedelta(hours=3)
        )
        result = execute_tool(
            self.engineer,
            'search_complaints',
            {'created_within_hours': 2},
        )
        self.assertEqual(result['count'], 0)
