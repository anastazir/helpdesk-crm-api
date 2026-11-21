from rest_framework import status

from apps.complaints.models import Complaint, ComplaintAssignment, IssueType
from apps.users.models import User
from apps.zones.models import EngineerZoneAssignment, Zone
from core.tests.base import BaseAPITest


class ZoneListTest(BaseAPITest):
    def test_all_authenticated_roles_can_list(self):
        for user in [self.admin, self.hd, self.engineer]:
            self.auth_as(user)
            response = self.client.get('/api/zones/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_returns_401(self):
        response = self.client.get('/api/zones/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CreateZoneTest(BaseAPITest):
    def test_admin_creates_zone(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/zones/', {'name': 'Zone West'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Zone.objects.filter(name='Zone West').exists())

    def test_hd_cannot_create_zone(self):
        self.auth_as(self.hd)
        response = self.client.post('/api/zones/', {'name': 'Zone West'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_engineer_cannot_create_zone(self):
        self.auth_as(self.engineer)
        response = self.client.post('/api/zones/', {'name': 'Zone West'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_name_returns_400(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/zones/', {'name': self.zone.name}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UpdateZoneTest(BaseAPITest):
    def test_admin_updates_zone_name(self):
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/zones/{self.zone.id}/', {'name': 'Zone Updated'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.zone.refresh_from_db()
        self.assertEqual(self.zone.name, 'Zone Updated')

    def test_admin_deactivates_zone(self):
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/zones/{self.zone.id}/', {'is_active': False}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.zone.refresh_from_db()
        self.assertFalse(self.zone.is_active)


class ZoneEngineersTest(BaseAPITest):
    def test_returns_engineers_in_zone(self):
        other_engineer = User.objects.create_user(
            email='other@crm.in', password='Eng@123',
            full_name='Other Engineer', role='engineer', phone='9876543210',
        )
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='added', changed_by=self.admin,
        )
        self.auth_as(self.admin)
        response = self.client.get(f'/api/zones/{self.zone.id}/engineers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        engineer_ids = [engineer['id'] for engineer in response.data['data']]
        self.assertIn(self.engineer.id, engineer_ids)
        self.assertNotIn(other_engineer.id, engineer_ids)

    def test_returns_active_complaint_count(self):
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='added', changed_by=self.admin,
        )
        issue = IssueType.objects.create(name='Networking', order=10)
        active = Complaint.objects.create(
            caller_phone='9876543210', zone=self.zone,
            status='in_progress', created_by=self.hd,
        )
        active.issues.set([issue])
        ComplaintAssignment.objects.create(
            complaint=active, engineer=self.engineer, assigned_by=self.hd,
        )
        closed = Complaint.objects.create(
            caller_phone='9876543211', zone=self.zone,
            status='closed', created_by=self.hd,
        )
        closed.issues.set([issue])
        ComplaintAssignment.objects.create(
            complaint=closed, engineer=self.engineer, assigned_by=self.hd,
        )

        self.auth_as(self.admin)
        response = self.client.get(f'/api/zones/{self.zone.id}/engineers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        engineer = next(
            engineer for engineer in response.data['data']
            if engineer['id'] == self.engineer.id
        )
        self.assertEqual(engineer['active_complaint_count'], 1)
