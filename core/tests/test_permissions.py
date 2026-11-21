from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.users.models import User
from core.permissions import IsAdmin, IsAdminOrHD


class IsAdminTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Admin@123',
            full_name='Admin User', role='admin',
        )
        self.hd = User.objects.create_user(
            email='hd@test.com', password='HD@123',
            full_name='HD User', role='helpdesk',
        )
        self.engineer = User.objects.create_user(
            email='eng@test.com', password='Eng@123',
            full_name='Engineer User', role='engineer',
        )

    def _request_for(self, user):
        request = self.factory.get('/')
        request.user = user
        return request

    def test_admin_user_is_allowed(self):
        self.assertTrue(IsAdmin().has_permission(self._request_for(self.admin), None))

    def test_hd_user_is_denied(self):
        self.assertFalse(IsAdmin().has_permission(self._request_for(self.hd), None))

    def test_engineer_is_denied(self):
        self.assertFalse(IsAdmin().has_permission(self._request_for(self.engineer), None))

    def test_unauthenticated_is_denied(self):
        self.assertFalse(IsAdmin().has_permission(self._request_for(AnonymousUser()), None))


class IsAdminOrHDTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Admin@123',
            full_name='Admin User', role='admin',
        )
        self.hd = User.objects.create_user(
            email='hd@test.com', password='HD@123',
            full_name='HD User', role='helpdesk',
        )
        self.engineer = User.objects.create_user(
            email='eng@test.com', password='Eng@123',
            full_name='Engineer User', role='engineer',
        )

    def _request_for(self, user):
        request = self.factory.get('/')
        request.user = user
        return request

    def test_admin_is_allowed(self):
        self.assertTrue(IsAdminOrHD().has_permission(self._request_for(self.admin), None))

    def test_hd_is_allowed(self):
        self.assertTrue(IsAdminOrHD().has_permission(self._request_for(self.hd), None))

    def test_engineer_is_denied(self):
        self.assertFalse(IsAdminOrHD().has_permission(self._request_for(self.engineer), None))
