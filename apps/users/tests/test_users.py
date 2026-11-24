from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.zones.models import EngineerZoneAssignment
from core.tests.base import BaseAPITest


class UserListTest(BaseAPITest):
    def test_admin_can_list_users(self):
        self.auth_as(self.admin)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data['data'])
        self.assertGreaterEqual(response.data['data']['count'], 3)

    def test_hd_cannot_list_users(self):
        self.auth_as(self.hd)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_engineer_cannot_list_users(self):
        self.auth_as(self.engineer)
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_role(self):
        self.auth_as(self.admin)
        response = self.client.get('/api/users/?role=engineer')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertTrue(results)
        self.assertTrue(all(user['role'] == 'engineer' for user in results))

    def test_search_by_name(self):
        User.objects.create_user(
            email='ravi@crm.in', password='Password@123',
            full_name='Ravi Kumar', role='engineer', phone='9876543210',
        )
        self.auth_as(self.admin)
        response = self.client.get('/api/users/?search=Ravi')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['data']['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['full_name'], 'Ravi Kumar')


class CreateUserTest(BaseAPITest):
    def payload(self, **overrides):
        data = {
            'full_name': 'New User',
            'email': 'new@crm.in',
            'phone': '9876543210',
            'password': 'Password@123',
            'role': 'helpdesk',
        }
        data.update(overrides)
        return data

    def test_admin_creates_hd_user(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/users/', self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='new@crm.in').exists())
        self.assertEqual(response.data['data']['role'], 'helpdesk')

    def test_admin_creates_engineer_with_zones(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/users/', self.payload(
            email='neweng@crm.in', role='engineer', zone_ids=[self.zone.id],
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        engineer = User.objects.get(email='neweng@crm.in')
        assignment = EngineerZoneAssignment.objects.filter(
            engineer=engineer, zone=self.zone, action='added'
        ).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.changed_by, self.admin)

    def test_duplicate_email_returns_400(self):
        self.auth_as(self.admin)
        response = self.client.post(
            '/api/users/', self.payload(email=self.hd.email), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields_returns_400(self):
        self.auth_as(self.admin)
        response = self.client.post('/api/users/', {
            'full_name': 'No Email User',
            'phone': '9876543210',
            'password': 'Password@123',
            'role': 'helpdesk',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data['errors'])

    def test_hd_cannot_create_user(self):
        self.auth_as(self.hd)
        response = self.client.post('/api/users/', self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DisableUserTest(BaseAPITest):
    def test_admin_disables_hd_user(self):
        self.auth_as(self.admin)
        response = self.client.post(f'/api/users/{self.hd.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.hd.refresh_from_db()
        self.assertFalse(self.hd.is_active)

    def test_cannot_disable_admin(self):
        self.auth_as(self.admin)
        response = self.client.post(f'/api/users/{self.admin.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_hd_cannot_disable_user(self):
        self.auth_as(self.hd)
        response = self.client.post(f'/api/users/{self.engineer.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EnableUserTest(BaseAPITest):
    def test_admin_enables_disabled_user(self):
        user = User.objects.create_user(
            email='disabled@crm.in', password='Password@123',
            full_name='Disabled User', role='engineer',
            phone='9876543210', is_active=False,
        )
        self.auth_as(self.admin)
        response = self.client.post(f'/api/users/{user.id}/enable/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class ResetPasswordTest(BaseAPITest):
    def test_admin_resets_password(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/users/{self.hd.id}/reset-password/',
            {'new_password': 'NewPassword@123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        login_client = APIClient()
        login_response = login_client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'NewPassword@123',
        }, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_hd_cannot_reset_password(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/users/{self.engineer.id}/reset-password/',
            {'new_password': 'NewPassword@123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EngineersListTest(BaseAPITest):
    def test_all_roles_can_list_engineers(self):
        for user in [self.admin, self.hd, self.engineer]:
            self.auth_as(user)
            response = self.client.get('/api/users/engineers/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_zone_id(self):
        other_engineer = User.objects.create_user(
            email='other@crm.in', password='Eng@123',
            full_name='Other Engineer', role='engineer', phone='9876543210',
        )
        self.assign_zone(self.engineer, self.zone)

        self.auth_as(self.admin)
        response = self.client.get(f'/api/users/engineers/?zone_id={self.zone.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        engineer_ids = [engineer['id'] for engineer in response.data['data']]
        self.assertIn(self.engineer.id, engineer_ids)
        self.assertNotIn(other_engineer.id, engineer_ids)


class ZoneAssignmentTest(BaseAPITest):
    def test_admin_assigns_zone_to_engineer(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/users/{self.engineer.id}/zones/',
            {'zone_id': self.zone.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EngineerZoneAssignment.objects.filter(
            engineer=self.engineer, zone=self.zone, action='added'
        ).exists())

    def test_admin_removes_zone_from_engineer(self):
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='added', changed_by=self.admin,
        )
        self.auth_as(self.admin)
        response = self.client.delete(
            f'/api/users/{self.engineer.id}/zones/{self.zone.id}/'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EngineerZoneAssignment.objects.filter(
            engineer=self.engineer, zone=self.zone, action='removed'
        ).exists())

    def test_duplicate_zone_assignment_returns_400(self):
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='added', changed_by=self.admin,
        )
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/users/{self.engineer.id}/zones/',
            {'zone_id': self.zone.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zone_history_returned(self):
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='added', changed_by=self.admin,
        )
        EngineerZoneAssignment.objects.create(
            engineer=self.engineer, zone=self.zone,
            action='removed', changed_by=self.admin,
        )
        self.auth_as(self.admin)
        response = self.client.get(f'/api/users/{self.engineer.id}/zone-history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 2)


class UserAuditAndDeleteTest(BaseAPITest):
    def test_admin_can_soft_delete_user_and_audit_is_written(self):
        self.auth_as(self.admin)
        response = self.client.delete(f'/api/users/{self.engineer.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.engineer.refresh_from_db()
        self.assertTrue(self.engineer.is_deleted)
        self.assertFalse(self.engineer.is_active)
        audit = self.client.get('/api/users/audit-logs/')
        self.assertEqual(audit.status_code, status.HTTP_200_OK)
        self.assertTrue(any(
            row['action'] == 'deleted' for row in audit.data['data']['results']
        ))

    def test_delete_blocked_by_active_assignment(self):
        complaint = self.make_complaint(status='assigned')
        self.assign_engineer(complaint, self.engineer)
        self.auth_as(self.admin)
        response = self.client.delete(f'/api/users/{self.engineer.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_helpdesk_cannot_read_audit_log(self):
        self.auth_as(self.hd)
        response = self.client.get('/api/users/audit-logs/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_email_and_phone_with_audit(self):
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/users/{self.engineer.id}/',
            {'email': 'new-engineer@test.com', 'phone': '9000000099'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.engineer.refresh_from_db()
        self.assertEqual(self.engineer.email, 'new-engineer@test.com')
        self.assertEqual(self.engineer.phone, '9000000099')


class UserWhatsAppConsentTest(BaseAPITest):
    def test_admin_enables_whatsapp_consent(self):
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/users/{self.engineer.id}/',
            {'whatsapp_opt_in': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.engineer.refresh_from_db()
        self.assertTrue(self.engineer.whatsapp_opt_in)
        self.assertIsNotNone(self.engineer.whatsapp_opt_in_at)
        self.assertEqual(self.engineer.whatsapp_opt_in_source, 'admin_form')

    def test_admin_disables_whatsapp_consent(self):
        self.engineer.whatsapp_opt_in = True
        self.engineer.save(update_fields=['whatsapp_opt_in'])
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/users/{self.engineer.id}/',
            {'whatsapp_opt_in': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.engineer.refresh_from_db()
        self.assertFalse(self.engineer.whatsapp_opt_in)
        self.assertIsNotNone(self.engineer.whatsapp_opt_out_at)

    def test_create_engineer_with_whatsapp_consent(self):
        self.auth_as(self.admin)
        response = self.client.post(
            '/api/users/',
            {
                'full_name': 'Consent Engineer',
                'email': 'consent@crm.in',
                'phone': '9876512345',
                'password': 'Password@123',
                'role': 'engineer',
                'whatsapp_opt_in': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        engineer = User.objects.get(email='consent@crm.in')
        self.assertTrue(engineer.whatsapp_opt_in)
        self.assertEqual(engineer.whatsapp_opt_in_source, 'admin_form')

    def test_phone_change_resets_whatsapp_consent(self):
        self.engineer.whatsapp_opt_in = True
        self.engineer.save(update_fields=['whatsapp_opt_in'])
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/users/{self.engineer.id}/',
            {'phone': '9876500011'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.engineer.refresh_from_db()
        self.assertFalse(self.engineer.whatsapp_opt_in)
        self.assertIsNotNone(self.engineer.whatsapp_opt_out_at)
