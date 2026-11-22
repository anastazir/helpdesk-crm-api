from rest_framework import status

from apps.complaints.models import FileUpload, JobNote, StatusHistory
from core.tests.base import BaseAPITest


class StatusTransitionTest(BaseAPITest):
    def prepare(self, complaint_status, assigned=True):
        complaint = self.make_complaint(status=complaint_status)
        if assigned:
            self.assign_engineer(complaint)
        return complaint

    def set_status(self, complaint, new_status, user, remark=None):
        self.auth_as(user)
        payload = {'status': new_status}
        if remark is not None:
            payload['remark'] = remark
        return self.client.post(
            f'/api/complaints/{complaint.id}/status/', payload, format='json'
        )

    def test_assigned_to_in_progress_by_engineer(self):
        complaint = self.prepare('assigned')
        response = self.set_status(complaint, 'in_progress', self.engineer)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'in_progress')

    def test_hd_cannot_set_in_progress(self):
        complaint = self.prepare('assigned')
        response = self.set_status(complaint, 'in_progress', self.hd)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parts_requested_to_parts_provided_by_hd(self):
        complaint = self.prepare('parts_requested')
        response = self.set_status(complaint, 'parts_provided', self.hd)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'parts_provided')

    def test_engineer_cannot_set_parts_provided(self):
        complaint = self.prepare('parts_requested')
        response = self.set_status(complaint, 'parts_provided', self.engineer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_in_progress_to_resolved_by_engineer(self):
        complaint = self.prepare('in_progress')
        FileUpload.objects.create(
            complaint=complaint,
            file='complaint_uploads/test.jpg',
            file_type='image',
            original_name='test.jpg',
            upload_batch=1,
            uploaded_by=self.engineer,
        )
        response = self.set_status(complaint, 'resolved', self.engineer)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'resolved')

    def test_resolve_requires_upload(self):
        complaint = self.prepare('in_progress')
        response = self.set_status(complaint, 'resolved', self.engineer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'in_progress')

    def test_resolved_to_closed_by_hd(self):
        complaint = self.prepare('resolved')
        response = self.set_status(complaint, 'closed', self.hd)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'closed')

    def test_invalid_transition_returns_400(self):
        complaint = self.prepare('open')
        response = self.set_status(complaint, 'resolved', self.hd)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_status_history_entry_created_on_each_change(self):
        complaint = self.prepare('assigned')
        self.set_status(complaint, 'in_progress', self.engineer)
        entries = StatusHistory.objects.filter(complaint=complaint)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().new_status, 'in_progress')
        self.assertEqual(entries.first().previous_status, 'assigned')

    def test_optional_remark_stored_in_history(self):
        complaint = self.prepare('assigned')
        self.set_status(
            complaint, 'in_progress', self.engineer, remark='On my way.'
        )
        entry = StatusHistory.objects.filter(
            complaint=complaint, new_status='in_progress'
        ).first()
        self.assertEqual(entry.remark, 'On my way.')

    def test_unassigned_engineer_cannot_change_status(self):
        complaint = self.prepare('assigned', assigned=False)
        response = self.set_status(complaint, 'in_progress', self.engineer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class JobNoteTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint(status='in_progress')
        self.assign_engineer(self.complaint)

    def test_engineer_submits_job_note(self):
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/job-note/',
            {'text': 'Need 1x replacement HDD, 500GB.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(JobNote.objects.filter(complaint=self.complaint).exists())

    def test_hd_cannot_submit_job_note(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/job-note/',
            {'text': 'Trying to submit.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_job_note_returns_400(self):
        JobNote.objects.create(
            complaint=self.complaint,
            text='Existing note.',
            created_by=self.engineer,
        )
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/job-note/',
            {'text': 'Second note.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_job_note_requires_in_progress_status(self):
        complaint = self.make_complaint(status='assigned')
        self.assign_engineer(complaint)
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{complaint.id}/job-note/',
            {'text': 'Need parts.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_job_note_auto_sets_parts_requested(self):
        self.auth_as(self.engineer)
        self.client.post(
            f'/api/complaints/{self.complaint.id}/job-note/',
            {'text': 'Need parts.'},
            format='json',
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'parts_requested')


class ReopenTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint(status='closed')

    def test_admin_reopens_closed_complaint(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/reopen/',
            {'remark': 'PDF was illegible.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'resolved')

    def test_hd_cannot_reopen(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/reopen/',
            {'remark': 'Please reopen.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reopen_requires_remark(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/reopen/',
            {'remark': ''},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reopen_only_works_on_closed(self):
        complaint = self.make_complaint(status='resolved')
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/complaints/{complaint.id}/reopen/',
            {'remark': 'Reopen attempt.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reopen_creates_history_entry(self):
        self.auth_as(self.admin)
        self.client.post(
            f'/api/complaints/{self.complaint.id}/reopen/',
            {'remark': 'PDF was illegible.'},
            format='json',
        )
        entry = StatusHistory.objects.filter(
            complaint=self.complaint,
            previous_status='closed',
            new_status='resolved',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.remark, 'PDF was illegible.')
