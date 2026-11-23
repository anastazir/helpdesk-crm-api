from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from core.tests.base import BaseAPITest


class LoginTest(BaseAPITest):
    def test_login_success_returns_tokens(self):
        response = self.client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertIn('user', response.data['data'])

    def test_login_wrong_password_returns_401(self):
        response = self.client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'WrongPassword',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data['success'])

    def test_login_nonexistent_email_returns_401(self):
        response = self.client.post('/api/auth/login/', {
            'email': 'unknown@crm.in',
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_disabled_account_returns_401(self):
        user = User.objects.create_user(
            email='disabled@crm.in', password='Pass@123',
            full_name='Disabled User', role='engineer',
            phone='9876543210', is_active=False,
        )
        response = self.client.post('/api/auth/login/', {
            'email': user.email,
            'password': 'Pass@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('disabled', response.data['message'].lower())

    def test_login_with_phone_identifier(self):
        response = self.client.post('/api/auth/login/', {
            'identifier': self.hd.phone,
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['user']['email'], self.hd.email)

    def test_login_normalizes_country_code_phone(self):
        response = self.client.post('/api/auth/login/', {
            'identifier': f'+91{self.hd.phone}',
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_rejects_malformed_phone(self):
        response = self.client.post('/api/auth/login/', {
            'identifier': '12345',
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_response_shape(self):
        response = self.client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'HD@123',
        }, format='json')
        self.assertEqual(
            set(response.data.keys()), {'success', 'message', 'data', 'errors'}
        )


class LogoutTest(BaseAPITest):
    def test_logout_blacklists_refresh_token(self):
        login_response = self.client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'HD@123',
        }, format='json')
        refresh = login_response.data['data']['refresh']

        self.client.force_authenticate(user=self.hd)
        logout_response = self.client.post(
            '/api/auth/logout/', {'refresh': refresh}, format='json'
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        fresh_client = APIClient()
        refresh_response = fresh_client.post(
            '/api/auth/token/refresh/', {'refresh': refresh}, format='json'
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeTest(BaseAPITest):
    def test_me_returns_current_user(self):
        self.auth_as(self.hd)
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['email'], self.hd.email)
        self.assertEqual(response.data['data']['role'], 'helpdesk')

    def test_me_unauthenticated_returns_401(self):
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenRefreshTest(BaseAPITest):
    def test_refresh_returns_new_access_token(self):
        login_response = self.client.post('/api/auth/login/', {
            'email': self.hd.email,
            'password': 'HD@123',
        }, format='json')
        refresh = login_response.data['data']['refresh']

        response = self.client.post(
            '/api/auth/token/refresh/', {'refresh': refresh}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data['data'])
