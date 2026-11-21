from rest_framework import status

from apps.complaints.models import Comment
from apps.users.models import User
from core.tests.base import BaseAPITest


class AddCommentTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()
        self.assign_engineer(self.complaint)

    def test_hd_can_comment(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Engineer has been notified.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Comment.objects.filter(
            complaint=self.complaint, author=self.hd
        ).exists())

    def test_admin_can_comment(self):
        self.auth_as(self.admin)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Admin comment.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_assigned_engineer_can_comment(self):
        self.auth_as(self.engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Reached the location.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unassigned_engineer_cannot_comment(self):
        other_engineer = User.objects.create_user(
            email='other-eng@test.com', password='Eng@123',
            full_name='Other Engineer', role='engineer', phone='9876543210',
        )
        self.auth_as(other_engineer)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Trying to comment.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_comment_on_closed_complaint(self):
        self.complaint.status = 'closed'
        self.complaint.save(update_fields=['status'])
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': 'Too late.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_body_returns_400(self):
        self.auth_as(self.hd)
        response = self.client.post(
            f'/api/complaints/{self.complaint.id}/comments/',
            {'body': ''},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EditCommentTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.complaint = self.make_complaint()

    def test_author_edits_own_last_comment(self):
        comment = Comment.objects.create(
            complaint=self.complaint, author=self.hd, body='Original body.'
        )
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/comments/{comment.id}/',
            {'body': 'Updated body.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.body, 'Updated body.')
        self.assertTrue(comment.is_edited)
        self.assertIsNotNone(comment.edited_at)

    def test_cannot_edit_when_someone_else_commented_after(self):
        comment = Comment.objects.create(
            complaint=self.complaint, author=self.hd, body='First.'
        )
        Comment.objects.create(
            complaint=self.complaint, author=self.admin, body='Second.'
        )
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/comments/{comment.id}/',
            {'body': 'Edited first.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_author_cannot_edit(self):
        comment = Comment.objects.create(
            complaint=self.complaint, author=self.hd, body='HD comment.'
        )
        self.auth_as(self.admin)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/comments/{comment.id}/',
            {'body': 'Admin edit.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_edit_on_closed_complaint(self):
        comment = Comment.objects.create(
            complaint=self.complaint, author=self.hd, body='Before close.'
        )
        self.complaint.status = 'closed'
        self.complaint.save(update_fields=['status'])
        self.auth_as(self.hd)
        response = self.client.patch(
            f'/api/complaints/{self.complaint.id}/comments/{comment.id}/',
            {'body': 'Too late.'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ListCommentsTest(BaseAPITest):
    def test_comments_returned_oldest_first(self):
        complaint = self.make_complaint()
        Comment.objects.create(complaint=complaint, author=self.hd, body='First')
        Comment.objects.create(complaint=complaint, author=self.admin, body='Second')
        Comment.objects.create(complaint=complaint, author=self.hd, body='Third')

        self.auth_as(self.hd)
        response = self.client.get(f'/api/complaints/{complaint.id}/comments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bodies = [comment['body'] for comment in response.data['data']]
        self.assertEqual(bodies, ['First', 'Second', 'Third'])
