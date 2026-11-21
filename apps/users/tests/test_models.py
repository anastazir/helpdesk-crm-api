from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.users.models import User


class UserModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='ravi@crm.in',
            password='Password@123',
            full_name='Ravi Kumar',
            role='engineer',
            phone='9876543210',
        )

    def test_create_user_sets_fields(self):
        self.assertEqual(self.user.email, 'ravi@crm.in')
        self.assertEqual(self.user.role, 'engineer')
        self.assertEqual(self.user.full_name, 'Ravi Kumar')
        self.assertTrue(self.user.is_active)

    def test_password_is_hashed(self):
        self.assertNotEqual(self.user.password, 'Password@123')
        self.assertTrue(self.user.check_password('Password@123'))

    def test_email_must_be_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    email='ravi@crm.in',
                    password='Password@123',
                    full_name='Other User',
                    role='helpdesk',
                    phone='9876543211',
                )

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertIsNone(authenticate(username='ravi@crm.in', password='Password@123'))

    def test_str_representation(self):
        self.assertEqual(str(self.user), 'Ravi Kumar (engineer)')
