from rest_framework import status

from apps.complaints.models import ComplaintAssignment, StatusHistory
from apps.users.models import User
from core.tests.base import BaseAPITest


class AssignEngineerTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def test_supervisor_assigns_engineer(self):
        self.auth_as(self.supervisor)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(ComplaintAssignment.objects.filter(
            complaint=self.complaint, engineer=self.engineer,
            unassigned_at__isnull=True,
        ).exists())
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'assigned')

    def test_admin_assigns_engineer(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_engineer_cannot_assign(self):
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hd_cannot_assign(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_creates_status_history_entry(self):
        self.auth_as(self.supervisor)
        self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        entry = StatusHistory.objects.filter(
            complaint=self.complaint, new_status='assigned'
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.previous_status, 'open')

    def test_cannot_assign_to_closed_complaint(self):
        closed = self.make_complaint(status='closed')
        self.auth_as(self.supervisor)
        response = self.client.post(
            f'/api/complaints/{closed.id}/assign/',
            {'engineer_id': self.engineer.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ReassignEngineerTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.other_engineer = User.objects.create_user(
            email='other-eng@test.com', password='Eng@123',
            full_name='Other Engineer', role='engineer', phone='9876543210',
        )
        self.complaint = self.make_complaint(status='assigned')
        self.assignment = self.assign_engineer(self.complaint, self.engineer)

    def reassign(self):
        self.auth_as(self.supervisor)
        return self.client.post(
            f'/api/complaints/{self.complaint.id}/assign/',
            {'engineer_id': self.other_engineer.id},
            format='json',
        )

    def test_reassign_closes_old_assignment(self):
        response = self.reassign()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertIsNotNone(self.assignment.unassigned_at)
        self.assertEqual(self.assignment.unassigned_by, self.supervisor)

    def test_reassign_creates_new_assignment(self):
        self.reassign()
        self.assertTrue(ComplaintAssignment.objects.filter(
            complaint=self.complaint, engineer=self.other_engineer,
            unassigned_at__isnull=True,
        ).exists())

    def test_only_one_active_assignment_at_a_time(self):
        self.reassign()
        active_count = ComplaintAssignment.objects.filter(
            complaint=self.complaint, unassigned_at__isnull=True
        ).count()
        self.assertEqual(active_count, 1)

    def test_old_engineer_loses_comment_access(self):
        self.reassign()
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Still here?'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AssignmentHistoryTest(BaseAPITest):
    def test_history_returns_all_records(self):
        complaint = self.make_complaint(status='assigned')
        self.assign_engineer(complaint, self.engineer)

        other_engineer = User.objects.create_user(
            email='other-eng@test.com', password='Eng@123',
            full_name='Other Engineer', role='engineer', phone='9876543210',
        )
        self.auth_as(self.supervisor)
        self.client.post(
            f'/api/complaints/{complaint.id}/assign/',
            {'engineer_id': other_engineer.id},
            format='json',
        )

        response = self.client.get(f'/api/complaints/{complaint.id}/assignments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 2)
