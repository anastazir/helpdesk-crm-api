from django.test import TestCase
from rest_framework import status

from core.responses import error_response, success_response


class SuccessResponseTest(TestCase):
    def setUp(self):
        self.response = success_response(data={'key': 'value'}, message='Done.')

    def test_shape_has_all_keys(self):
        self.assertEqual(
            set(self.response.data.keys()),
            {'success', 'message', 'data', 'errors'},
        )

    def test_success_is_true(self):
        self.assertIs(self.response.data['success'], True)

    def test_errors_is_none(self):
        self.assertIsNone(self.response.data['errors'])

    def test_default_status_code_is_200(self):
        self.assertEqual(self.response.status_code, status.HTTP_200_OK)


class ErrorResponseTest(TestCase):
    def setUp(self):
        self.response = error_response(message='Bad request.')

    def test_success_is_false(self):
        self.assertIs(self.response.data['success'], False)

    def test_data_is_none(self):
        self.assertIsNone(self.response.data['data'])

    def test_default_status_code_is_400(self):
        self.assertEqual(self.response.status_code, status.HTTP_400_BAD_REQUEST)
