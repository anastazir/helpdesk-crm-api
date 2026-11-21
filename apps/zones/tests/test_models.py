from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.users.models import User
from apps.zones.models import Zone


class ZoneModelTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@test.com', password='Admin@123',
            full_name='Admin User', role='admin', phone='9876543210',
        )
        self.zone = Zone.objects.create(name='Zone North', created_by=self.admin)

    def test_zone_name_is_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Zone.objects.create(name='Zone North', created_by=self.admin)

    def test_zone_defaults_to_active(self):
        self.assertTrue(self.zone.is_active)

    def test_str_representation(self):
        self.assertEqual(str(self.zone), 'Zone North')
