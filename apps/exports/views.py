import logging
from datetime import date
from io import BytesIO

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from core.permissions import IsAdminOrHD
from core.responses import error_response, success_response

from .builder import (
    build_workbook,
    deduplicate_complaints,
    get_column_value,
    get_matching_complaints,
)
from .serializers import COLUMN_HEADERS, ExportDownloadSerializer, ExportPreviewSerializer

logger = logging.getLogger('apps.exports')


@extend_schema(tags=['export'])
class ExportPreviewView(APIView):
    permission_classes = [IsAdminOrHD]
    serializer_class = ExportPreviewSerializer

    @extend_schema(
        tags=['export'],
        request=ExportPreviewSerializer,
        responses={200: ExportPreviewSerializer},
    )
    def post(self, request):
        serializer = ExportPreviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        filters = serializer.validated_data.get('filters') or {}
        deduplicate = serializer.validated_data.get('deduplicate', False)
        if 'columns' in serializer.validated_data:
            columns = serializer.validated_data.get('columns') or []
        else:
            columns = list(COLUMN_HEADERS.keys())

        all_matching = get_matching_complaints(filters=filters, deduplicate=False)
        if deduplicate:
            matching = deduplicate_complaints(all_matching)
        else:
            matching = all_matching

        total_matching_count = len(all_matching)
        after_deduplication = len(matching)
        preview_complaints = matching[:10]

        rows = [
            {
                column: get_column_value(complaint, column)
                for column in columns
            }
            for complaint in preview_complaints
        ]

        return success_response(data={
            'total_matching': total_matching_count,
            'after_deduplication': after_deduplication,
            'deduplicated_count': total_matching_count - after_deduplication,
            'columns': columns,
            'rows': rows,
        })


@extend_schema(tags=['export'])
class ExportDownloadView(APIView):
    permission_classes = [IsAdminOrHD]
    serializer_class = ExportDownloadSerializer

    @extend_schema(
        tags=['export'],
        request=ExportDownloadSerializer,
        responses={
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
                OpenApiTypes.BINARY
        },
    )
    def post(self, request):
        serializer = ExportDownloadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        filters = serializer.validated_data.get('filters') or {}
        deduplicate = serializer.validated_data.get('deduplicate', False)
        columns = serializer.validated_data['effective_columns']

        complaints = get_matching_complaints(filters=filters, deduplicate=deduplicate)
        workbook = build_workbook(complaints, columns)

        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        logger.info(
            f'[EXPORT] {request.user.email} exported {len(complaints)} complaints'
        )

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            status=status.HTTP_200_OK,
        )
        response['Content-Disposition'] = (
            f'attachment; filename="complaints_export_{date.today():%Y%m%d}.xlsx"'
        )
        return response
