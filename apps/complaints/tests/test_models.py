from datetime import timedelta

from django.utils import timezone

from apps.complaints.models import ComplaintAssignment, StatusHistory
from core.tests.base import BaseAPITest


class ComplaintIDTest(BaseAPITest):
    def test_first_complaint_id_is_100001(self):
        complaint = self.make_complaint()
        self.assertEqual(complaint.id, 100001)

    def test_id_increments_sequentially(self):
        first = self.make_complaint()
        second = self.make_complaint()
        self.assertEqual(first.id, 100001)
        self.assertEqual(second.id, 100002)

    def test_id_is_not_overwritable(self):
        complaint = self.make_complaint()
        original_id = complaint.id
        complaint.status = 'assigned'
        complaint.save()
        complaint.refresh_from_db()
        self.assertEqual(complaint.id, original_id)


class ComplaintTimeTest(BaseAPITest):
    def test_time_open_counts_from_created_at(self):
        complaint = self.make_complaint()
        seconds = complaint.get_time_open_seconds()
        self.assertGreaterEqual(seconds, 0)
        self.assertLess(seconds, 10)

    def test_time_open_stops_at_closed_timestamp(self):
        complaint = self.make_complaint(status='closed')
        closed_time = complaint.created_at + timedelta(seconds=100)
        entry = StatusHistory.objects.create(
            complaint=complaint,
            previous_status='resolved',
            new_status='closed',
            changed_by=self.hd,
        )
        StatusHistory.objects.filter(pk=entry.pk).update(changed_at=closed_time)

        seconds = complaint.get_time_open_seconds()
        self.assertAlmostEqual(seconds, 100, delta=2)

    def test_time_in_status_counts_from_last_history(self):
        complaint = self.make_complaint()
        entry = StatusHistory.objects.create(
            complaint=complaint,
            previous_status=None,
            new_status='open',
            changed_by=self.hd,
        )
        StatusHistory.objects.filter(pk=entry.pk).update(
            changed_at=timezone.now() - timedelta(seconds=60)
        )

        seconds = complaint.get_time_in_status_seconds()
        self.assertAlmostEqual(seconds, 60, delta=3)


class ComplaintAssignmentTest(BaseAPITest):
    def test_get_current_assignment_returns_active(self):
        complaint = self.make_complaint()
        assignment = ComplaintAssignment.objects.create(
            complaint=complaint, engineer=self.engineer, assigned_by=self.hd,
        )
        self.assertEqual(complaint.get_current_assignment(), assignment)

    def test_get_current_assignment_returns_none(self):
        complaint = self.make_complaint()
        ComplaintAssignment.objects.create(
            complaint=complaint,
            engineer=self.engineer,
            assigned_by=self.hd,
            unassigned_at=timezone.now(),
            unassigned_by=self.hd,
        )
        self.assertIsNone(complaint.get_current_assignment())
