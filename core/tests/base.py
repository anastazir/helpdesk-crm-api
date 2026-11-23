from rest_framework.test import APIClient, APITestCase

from apps.complaints.models import (
    Complaint,
    ComplaintAssignment,
    IssueType,
    StatusHistory,
)
from apps.users.models import User
from apps.zones.models import EngineerZoneAssignment, Zone


class BaseAPITest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Admin@123',
            full_name='Admin User', role='admin', phone='9000000001',
        )
        self.supervisor = User.objects.create_user(
            email='supervisor@test.com', password='Super@123',
            full_name='Supervisor User', role='supervisor', phone='9000000002',
        )
        self.hd = User.objects.create_user(
            email='hd@test.com', password='HD@123',
            full_name='HD User', role='helpdesk', phone='9000000003',
        )
        self.engineer = User.objects.create_user(
            email='eng@test.com', password='Eng@123',
            full_name='Engineer User', role='engineer', phone='9000000004',
        )
        self.zone = Zone.objects.create(name='Test Zone', created_by=self.admin)
        self.issue = IssueType.objects.create(name='Monitor', order=9)
        self.client = APIClient()

    def auth_as(self, user):
        """Authenticate the test client as a given user."""
        self.client.force_authenticate(user=user)

    def make_complaint(self, created_by=None, zone=None, status='open', **kwargs):
        """Factory: creates a minimal valid complaint."""
        complaint = Complaint.objects.create(
            caller_phone=kwargs.pop('caller_phone', '9876543210'),
            zone=zone or self.zone,
            status=status,
            created_by=created_by or self.hd,
            **kwargs,
        )
        complaint.issues.set([self.issue])
        return complaint

    def assign_engineer(self, complaint, engineer=None, assigned_by=None):
        return ComplaintAssignment.objects.create(
            complaint=complaint,
            engineer=engineer or self.engineer,
            assigned_by=assigned_by or self.hd,
        )

    def add_status_history(self, complaint, previous_status, new_status,
                           changed_by=None, remark=None):
        return StatusHistory.objects.create(
            complaint=complaint,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=changed_by or self.hd,
            remark=remark,
        )

    def assign_zone(self, engineer, zone=None, changed_by=None):
        return EngineerZoneAssignment.objects.create(
            engineer=engineer,
            zone=zone or self.zone,
            action='added',
            changed_by=changed_by or self.admin,
        )
