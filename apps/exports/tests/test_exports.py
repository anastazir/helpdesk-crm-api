from io import BytesIO

from openpyxl import load_workbook
from rest_framework import status

from core.tests.base import BaseAPITest


class ExportPreviewTest(BaseAPITest):
    def preview(self, payload=None):
        return self.client.post(
            '/api/export/preview/',
            payload or {'filters': {}, 'deduplicate': False},
            format='json',
        )

    def test_hd_gets_preview_counts(self):
        self.make_complaint()
        self.make_complaint()
        self.auth_as(self.hd)
        response = self.preview()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_matching', response.data['data'])
        self.assertIn('after_deduplication', response.data['data'])

    def test_admin_gets_preview_counts(self):
        self.make_complaint()
        self.auth_as(self.admin)
        response = self.preview()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_engineer_cannot_preview(self):
        self.auth_as(self.engineer)
        response = self.preview()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_status_reduces_count(self):
        self.make_complaint(status='open')
        self.make_complaint(status='open')
        self.make_complaint(status='closed')
        self.auth_as(self.hd)
        response = self.preview({
            'filters': {'status': 'open'},
            'deduplicate': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['total_matching'], 2)

    def test_deduplication_removes_older_duplicates(self):
        self.make_complaint(cpu_serial='CPU-001')
        self.make_complaint(cpu_serial='CPU-001')
        self.auth_as(self.hd)
        response = self.preview({'filters': {}, 'deduplicate': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['total_matching'], 2)
        self.assertEqual(data['after_deduplication'], 1)
        self.assertEqual(data['deduplicated_count'], 1)

    def test_null_cpu_serial_always_included_in_dedup(self):
        self.make_complaint()
        self.make_complaint()
        self.make_complaint()
        self.make_complaint(cpu_serial='CPU-SHARED')
        self.make_complaint(cpu_serial='CPU-SHARED')
        self.auth_as(self.hd)
        response = self.preview({'filters': {}, 'deduplicate': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['after_deduplication'], 4)


class ExportDownloadTest(BaseAPITest):
    def download(self, payload):
        return self.client.post('/api/export/download/', payload, format='json')

    def test_hd_downloads_excel(self):
        self.make_complaint()
        self.auth_as(self.hd)
        response = self.download({
            'columns': ['id', 'caller_name'],
            'filters': {},
            'deduplicate': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertTrue(response.content)

    def test_admin_downloads_excel(self):
        self.make_complaint()
        self.auth_as(self.admin)
        response = self.download({
            'columns': ['id'],
            'filters': {},
            'deduplicate': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content)

    def test_engineer_cannot_download(self):
        self.auth_as(self.engineer)
        response = self.download({
            'columns': ['id'],
            'filters': {},
            'deduplicate': False,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_column_order_matches_request(self):
        self.make_complaint()
        self.auth_as(self.hd)
        response = self.download({
            'columns': ['id', 'caller_name', 'caller_phone', 'zone', 'status'],
            'column_order': ['status', 'id'],
            'filters': {},
            'deduplicate': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        headers = [worksheet.cell(row=1, column=index).value for index in range(1, 3)]
        self.assertEqual(headers, ['Status', 'Complaint ID'])

    def test_row_count_matches_preview(self):
        self.make_complaint(cpu_serial='CPU-DUP')
        self.make_complaint(cpu_serial='CPU-DUP')
        self.make_complaint()

        self.auth_as(self.hd)
        preview = self.client.post('/api/export/preview/', {
            'filters': {},
            'deduplicate': True,
        }, format='json')
        expected_rows = preview.data['data']['after_deduplication']

        response = self.download({
            'columns': ['id'],
            'filters': {},
            'deduplicate': True,
        })
        workbook = load_workbook(BytesIO(response.content))
        worksheet = workbook.active
        self.assertEqual(worksheet.max_row - 1, expected_rows)
