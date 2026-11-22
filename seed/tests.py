from django.core.management import call_command
from django.test import TestCase

from apps.complaints.models import Complaint
from apps.users.models import User
from apps.zones.models import Zone

from .management.commands.seed_data import MCD_ZONE_NAMES


class SeedDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_data', verbosity=0)

    def test_seed_uses_real_mcd_zones(self):
        self.assertEqual(
            set(Zone.objects.values_list('name', flat=True)),
            set(MCD_ZONE_NAMES),
        )
        self.assertEqual(Zone.objects.count(), 12)

    def test_every_zone_has_at_least_two_active_engineers(self):
        self.assertEqual(
            User.objects.filter(role='engineer', is_active=True).count(),
            12,
        )
        for zone in Zone.objects.all():
            with self.subTest(zone=zone.name):
                self.assertGreaterEqual(zone.get_engineer_count(), 2)

    def test_complaints_only_use_mcd_zones(self):
        self.assertEqual(Complaint.objects.count(), 25)
        self.assertFalse(
            Complaint.objects.exclude(zone__name__in=MCD_ZONE_NAMES).exists()
        )
