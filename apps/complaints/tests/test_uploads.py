import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from apps.complaints.models import FileUpload
from core.tests.base import BaseAPITest

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def image_file(name='photo.jpg', content=b'fake-image-content'):
    return SimpleUploadedFile(name, content, content_type='image/jpeg')


def pdf_file(name='report.pdf', content=b'fake-pdf-content'):
    return SimpleUploadedFile(name, content, content_type='application/pdf')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FileUploadTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint(status='in_progress')
        self.assign_engineer(self.complaint)

    def upload(self, files, user=None):
        self.auth_as(user or self.engineer)
        return self.client.post(
            f'/api/complaints/{self.complaint.id}/uploads/',
            {'files': files},
            format='multipart',
        )

    def test_assigned_engineer_uploads_images(self):
        response = self.upload([image_file('one.jpg'), image_file('two.png')])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        uploads = FileUpload.objects.filter(complaint=self.complaint)
        self.assertEqual(uploads.count(), 2)
        self.assertTrue(all(upload.file_type == 'image' for upload in uploads))

    def test_assigned_engineer_uploads_pdf(self):
        response = self.upload([pdf_file()])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        upload = FileUpload.objects.get(complaint=self.complaint)
        self.assertEqual(upload.file_type, 'pdf')

    def test_unassigned_engineer_cannot_upload(self):
        self.complaint.assignments.update(unassigned_at=self.complaint.created_at)
        response = self.upload([image_file()])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hd_cannot_upload(self):
        response = self.upload([image_file()], user=self.hd)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_upload_to_closed_complaint(self):
        self.complaint.status = 'closed'
        self.complaint.save(update_fields=['status'])
        response = self.upload([image_file()])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_max_3_images_enforced(self):
        response = self.upload([image_file(f'{index}.jpg') for index in range(4)])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_max_1_pdf_enforced(self):
        response = self.upload([pdf_file('one.pdf'), pdf_file('two.pdf')])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_mix_images_and_pdf(self):
        response = self.upload([image_file(), pdf_file()])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_number_increments(self):
        self.upload([image_file('first.jpg')])
        self.upload([image_file('second.jpg')])
        batches = sorted(
            FileUpload.objects.filter(complaint=self.complaint)
            .values_list('upload_batch', flat=True)
        )
        self.assertEqual(batches, [1, 2])

    def test_first_upload_is_batch_1(self):
        self.upload([image_file()])
        upload = FileUpload.objects.get(complaint=self.complaint)
        self.assertEqual(upload.upload_batch, 1)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class UploadHistoryTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint(status='in_progress')
        self.assign_engineer(self.complaint)
        self.auth_as(self.engineer)
        self.client.post(
            f'/api/complaints/{self.complaint.id}/uploads/',
            {'files': [image_file('batch1.jpg')]},
            format='multipart',
        )
        self.client.post(
            f'/api/complaints/{self.complaint.id}/uploads/',
            {'files': [image_file('batch2.jpg'), image_file('batch2b.jpg')]},
            format='multipart',
        )

    def test_all_batches_returned(self):
        response = self.client.get(f'/api/complaints/{self.complaint.id}/uploads/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 2)
        batch_numbers = [batch['batch_number'] for batch in response.data['data']]
        self.assertEqual(sorted(batch_numbers), [1, 2])

    def test_batches_ordered_newest_first(self):
        response = self.client.get(f'/api/complaints/{self.complaint.id}/uploads/')
        batch_numbers = [batch['batch_number'] for batch in response.data['data']]
        self.assertEqual(batch_numbers, [2, 1])
