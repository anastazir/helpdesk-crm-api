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

from .builder import build_workbook, get_matching_complaints
from .serializers import ExportDownloadSerializer, ExportPreviewSerializer

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

        complaints = get_matching_complaints(filters=filters, deduplicate=deduplicate)
        after_deduplication = len(complaints)

        total_matching = get_matching_complaints(
            filters=filters, deduplicate=False
        )
        total_matching_count = len(total_matching)

        return success_response(data={
            'total_matching': total_matching_count,
            'after_deduplication': after_deduplication,
            'deduplicated_count': total_matching_count - after_deduplication,
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
