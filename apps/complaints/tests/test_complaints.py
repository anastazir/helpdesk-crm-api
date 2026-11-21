from rest_framework import status

from apps.complaints.models import Complaint, IssueType, StatusHistory
from apps.zones.models import Zone
from core.tests.base import BaseAPITest


class CreateComplaintTest(BaseAPITest):
    def payload(self, **overrides):
        data = {
            'caller_phone': '9876543210',
            'caller_name': 'Rajesh Kumar',
            'zone_id': self.zone.id,
            'issue_ids': [self.issue.id],
        }
        data.update(overrides)
        return data

    def test_hd_creates_complaint(self):
        self.auth_as(self.hd)
        response = self.client.post('/api/complaints/', self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(response.data['data']['id'], 100001)

    def test_admin_creates_complaint(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/complaints/', self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_engineer_cannot_create(self):
        self.auth_as(self.engineer)
        response = self.client.post('/api/complaints/', self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_caller_phone_returns_400(self):
        self.auth_as(self.hd)
        data = self.payload()
        data.pop('caller_phone')
        response = self.client.post('/api/complaints/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_issues_returns_400(self):
        self.auth_as(self.hd)
        data = self.payload()
        data.pop('issue_ids')
        response = self.client.post('/api/complaints/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_others_issue_requires_description(self):
        others = IssueType.objects.create(name='Others', order=16)
        self.auth_as(self.hd)
        response = self.client.post('/api/complaints/', self.payload(
            issue_ids=[others.id]
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('others_description', response.data['errors'])

    def test_initial_status_is_open(self):
        self.auth_as(self.hd)
        response = self.client.post('/api/complaints/', self.payload(), format='json')
        self.assertEqual(response.data['data']['status'], 'open')
        complaint = Complaint.objects.get(pk=response.data['data']['id'])
        self.assertEqual(complaint.status, 'open')

    def test_initial_status_history_entry_created(self):
        self.auth_as(self.hd)
        response = self.client.post('/api/complaints/', self.payload(), format='json')
        history = StatusHistory.objects.filter(
            complaint_id=response.data['data']['id']
        )
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().new_status, 'open')
        self.assertIsNone(history.first().previous_status)


class ListComplaintsTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint_one = self.make_complaint()
        self.complaint_two = self.make_complaint(caller_phone='9876543211')

    def test_admin_sees_all_complaints(self):
        self.auth_as(self.admin)
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 2)
        self.assertIn('caller_phone', results[0])

    def test_hd_sees_all_complaints(self):
        self.auth_as(self.hd)
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['results']), 2)

    def test_engineer_gets_limited_data(self):
        self.auth_as(self.engineer)
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertTrue(results)
        for result in results:
            self.assertEqual(
                set(result.keys()),
                {'id', 'zone', 'address', 'status', 'created_at'},
            )

    def test_filter_by_status(self):
        closed = self.make_complaint(status='closed')
        self.auth_as(self.admin)
        response = self.client.get('/api/complaints/?status=open')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item['status'] == 'open' for item in results))
        self.assertNotIn(closed.id, [item['id'] for item in results])

    def test_filter_by_zone(self):
        other_zone = Zone.objects.create(name='Other Zone', created_by=self.admin)
        self.make_complaint(zone=other_zone)
        self.auth_as(self.admin)
        response = self.client.get(f'/api/complaints/?zone={self.zone.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item['zone']['id'] == self.zone.id for item in results))

    def test_search_by_complaint_id(self):
        self.auth_as(self.admin)
        response = self.client.get(
            f'/api/complaints/?search={self.complaint_one.id}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.complaint_one.id)


class ComplaintDetailTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def test_admin_gets_full_detail(self):
        self.auth_as(self.admin)
        response = self.client.get(f'/api/complaints/{self.complaint.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        for field in [
            'caller_phone', 'caller_name', 'bmid', 'aadhaar', 'zone',
            'issues', 'status', 'created_by', 'assigned_engineer', 'job_note',
            'time_open_seconds', 'time_in_status_seconds',
        ]:
            self.assertIn(field, data)

    def test_hd_gets_full_detail(self):
        self.auth_as(self.hd)
        response = self.client.get(f'/api/complaints/{self.complaint.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('caller_phone', response.data['data'])

    def test_assigned_engineer_gets_full_detail(self):
        self.assign_engineer(self.complaint)
        self.auth_as(self.engineer)
        response = self.client.get(f'/api/complaints/{self.complaint.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['id'], self.complaint.id)

    def test_unassigned_engineer_gets_403(self):
        self.auth_as(self.engineer)
        response = self.client.get(f'/api/complaints/{self.complaint.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EditComplaintTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def test_hd_can_edit_caller_name(self):
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'caller_name': 'Updated Name'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.caller_name, 'Updated Name')

    def test_hd_can_edit_address(self):
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'address': 'New Address'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.address, 'New Address')

    def test_zone_is_not_editable(self):
        other_zone = Zone.objects.create(name='Other Zone', created_by=self.admin)
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'zone': other_zone.id, 'zone_id': other_zone.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.zone, self.zone)

    def test_bmid_is_not_editable(self):
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'bmid': 'BM-CHANGED'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertNotEqual(self.complaint.bmid, 'BM-CHANGED')

    def test_issues_not_editable(self):
        other_issue = IssueType.objects.create(name='Printer', order=8)
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'issue_ids': [other_issue.id]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(
            list(self.complaint.issues.values_list('id', flat=True)),
            [self.issue.id],
        )

    def test_cannot_edit_closed_complaint(self):
        closed = self.make_complaint(status='closed')
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{closed.id}/',
            {'caller_name': 'Nope'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_engineer_can_set_blank_cpu_serial(self):
        self.complaint.cpu_serial = None
        self.complaint.save(update_fields=['cpu_serial'])
        self.assign_engineer(self.complaint)
        self.auth_as(self.engineer)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'cpu_serial': 'SN-NEW-001'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.cpu_serial, 'SN-NEW-001')

    def test_engineer_cannot_overwrite_cpu_serial(self):
        self.complaint.cpu_serial = 'SN-OLD-001'
        self.complaint.save(update_fields=['cpu_serial'])
        self.assign_engineer(self.complaint)
        self.auth_as(self.engineer)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'cpu_serial': 'SN-NEW-001'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.cpu_serial, 'SN-OLD-001')

    def test_engineer_cannot_edit_caller_name(self):
        self.assign_engineer(self.complaint)
        self.auth_as(self.engineer)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/',
            {'caller_name': 'Engineer Edit'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertNotEqual(self.complaint.caller_name, 'Engineer Edit')
