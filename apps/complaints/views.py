import logging

from django.db.models import Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.assistant.geocoding import GeocodeServiceError, geocode_location
from apps.users.models import User
from apps.users.serializers import UserMiniSerializer
from core.pagination import StandardPagination
from core.permissions import IsAdmin, IsAdminOrHD, IsEngineer
from core.responses import error_response, success_response

from .models import (
    VALID_STATUS_TRANSITIONS,
    Comment,
    Complaint,
    ComplaintAssignment,
    FileUpload,
    IssueType,
    JobNote,
    StatusHistory,
)
from .serializers import (
    AssignSerializer,
    AssignmentSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    ComplaintCreateSerializer,
    ComplaintDetailSerializer,
    ComplaintListSerializer,
    ComplaintUpdateSerializer,
    EngineerLimitedComplaintSerializer,
    IssueTypeSerializer,
    JobNoteCreateSerializer,
    ManualLocationSerializer,
    JobNoteSerializer,
    ReopenSerializer,
    StatusHistorySerializer,
    StatusUpdateSerializer,
    UploadFileSerializer,
)

logger = logging.getLogger('apps.complaints')

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}


def _split_query_values(request, name):
    values = []
    for raw in request.query_params.getlist(name):
        values.extend(part.strip() for part in raw.split(',') if part.strip())
    return values


def _parse_integer_values(values):
    try:
        return [int(value) for value in values]
    except (TypeError, ValueError):
        return None

DEDICATED_TRANSITIONS = {
    ('open', 'assigned'): 'Use the assign endpoint to assign an engineer.',
    ('in_progress', 'parts_requested'): 'Use the job-note endpoint to request parts.',
    ('closed', 'resolved'): 'Use the reopen endpoint to reopen a closed complaint.',
}

ENGINEER_TRANSITIONS = {
    ('assigned', 'in_progress'),
    ('in_progress', 'resolved'),
    ('parts_provided', 'resolved'),
}

HD_TRANSITIONS = {
    ('parts_requested', 'parts_provided'),
    ('resolved', 'closed'),
}


@extend_schema(tags=['issues'])
class IssueTypeListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['issues'], responses={200: IssueTypeSerializer(many=True)})
    def get(self, request):
        issues = IssueType.objects.filter(is_active=True).order_by('order')
        return success_response(data=IssueTypeSerializer(issues, many=True).data)


@extend_schema(tags=['complaints'])
class ComplaintViewSet(viewsets.GenericViewSet):
    queryset = Complaint.objects.select_related('zone', 'created_by').prefetch_related('issues')
    serializer_class = ComplaintDetailSerializer
    pagination_class = StandardPagination

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdminOrHD()]
        if self.action == 'my':
            return [IsEngineer()]
        if self.action == 'assign':
            return [IsAdminOrHD()]
        if self.action == 'reopen':
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ComplaintCreateSerializer
        if self.action == 'partial_update':
            return ComplaintUpdateSerializer
        if self.action == 'list':
            if self.request.user.role == 'engineer':
                return EngineerLimitedComplaintSerializer
            return ComplaintListSerializer
        return ComplaintDetailSerializer

    def _is_currently_assigned_engineer(self, complaint, user):
        assignment = complaint.get_current_assignment()
        return assignment is not None and assignment.engineer_id == user.id

    def _can_view(self, complaint, user):
        if user.role in ['admin', 'helpdesk']:
            return True
        return self._is_currently_assigned_engineer(complaint, user)

    def _get_detail_response(self, complaint, message='', status_code=status.HTTP_200_OK):
        complaint = Complaint.objects.select_related('zone', 'created_by').prefetch_related(
            'issues'
        ).get(pk=complaint.pk)
        return success_response(
            data=ComplaintDetailSerializer(complaint).data,
            message=message,
            status_code=status_code,
        )

    @extend_schema(tags=['complaints'], responses={200: ComplaintListSerializer(many=True)})
    def list(self, request):
        queryset = self.get_queryset()

        status_values = _split_query_values(request, 'status')
        if status_values:
            queryset = queryset.filter(status__in=status_values)

        zone_values = _parse_integer_values(_split_query_values(request, 'zone'))
        if zone_values is None:
            return error_response('Invalid zone filter.', 'zone must be an integer.')
        if zone_values:
            queryset = queryset.filter(zone_id__in=zone_values)

        engineer_values = _parse_integer_values(
            _split_query_values(request, 'assigned_engineer')
        )
        if engineer_values is None:
            return error_response(
                'Invalid assigned_engineer filter.',
                'assigned_engineer must be an integer.',
            )
        if engineer_values:
            queryset = queryset.filter(
                assignments__engineer_id__in=engineer_values,
                assignments__unassigned_at__isnull=True,
            ).distinct()

        date_from = request.query_params.get('date_from')
        if date_from:
            parsed = parse_date(date_from)
            if parsed is None:
                return error_response('Invalid date_from.', 'Use an ISO date (YYYY-MM-DD).')
            queryset = queryset.filter(created_at__date__gte=parsed)

        date_to = request.query_params.get('date_to')
        if date_to:
            parsed = parse_date(date_to)
            if parsed is None:
                return error_response('Invalid date_to.', 'Use an ISO date (YYYY-MM-DD).')
            queryset = queryset.filter(created_at__date__lte=parsed)

        search = request.query_params.get('search')
        if search:
            search_filter = Q(caller_name__icontains=search) | Q(caller_phone__icontains=search)
            if search.isdigit():
                search_filter |= Q(id=int(search))
            queryset = queryset.filter(search_filter)

        ordering = request.query_params.get('ordering', 'created_at')
        if ordering == 'updated_at':
            queryset = queryset.annotate(
                last_status_change=Max('status_history__changed_at')
            ).order_by('-last_status_change', '-created_at')
        else:
            queryset = queryset.order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if request.user.role == 'engineer':
            serializer = EngineerLimitedComplaintSerializer(page, many=True)
        else:
            serializer = ComplaintListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(tags=['complaints'], request=ComplaintCreateSerializer)
    def create(self, request):
        serializer = ComplaintCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        data = dict(serializer.validated_data)
        issue_ids = data.pop('issue_ids')
        zone_id = data.pop('zone_id', None)
        if data.get('latitude') is not None and data.get('longitude') is not None:
            data['geocode_updated_at'] = timezone.now()

        complaint = Complaint.objects.create(
            zone_id=zone_id,
            created_by=request.user,
            **data,
        )
        complaint.issues.set(issue_ids)

        StatusHistory.objects.create(
            complaint=complaint,
            previous_status=None,
            new_status='open',
            changed_by=request.user,
            remark=None,
        )

        logger.info(f'[COMPLAINT] Created #{complaint.id} by {request.user.email}')
        return self._get_detail_response(
            complaint,
            message='Complaint created successfully.',
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(tags=['complaints'], responses={200: ComplaintDetailSerializer(many=True)})
    @action(detail=False, methods=['get'])
    def my(self, request):
        queryset = self.get_queryset().filter(
            assignments__engineer=request.user,
            assignments__unassigned_at__isnull=True,
        ).distinct().order_by('-created_at')

        page = self.paginate_queryset(queryset)
        serializer = ComplaintDetailSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(tags=['complaints'], responses={200: ComplaintDetailSerializer})
    def retrieve(self, request, pk=None):
        complaint = self.get_object()
        if not self._can_view(complaint, request.user):
            return error_response(
                'You do not have access to this complaint.',
                'You do not have access to this complaint.',
                status.HTTP_403_FORBIDDEN,
            )
        return self._get_detail_response(complaint)

    @extend_schema(tags=['complaints'], request=ComplaintUpdateSerializer)
    def partial_update(self, request, pk=None):
        complaint = self.get_object()

        if not self._can_view(complaint, request.user):
            return error_response(
                'You do not have access to this complaint.',
                'You do not have access to this complaint.',
                status.HTTP_403_FORBIDDEN,
            )

        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be edited.',
                'Closed complaints cannot be edited.',
                status.HTTP_403_FORBIDDEN,
            )

        if request.user.role == 'engineer':
            update_data = {}
            for field, label in [
                ('cpu_serial', 'CPU'),
                ('monitor_serial', 'Monitor'),
            ]:
                if field in request.data:
                    current_value = getattr(complaint, field)
                    if current_value and str(current_value).strip():
                        return error_response(
                            f'{label} serial number is already recorded. '
                            'Only Help Desk or Admin can change it.',
                            f'{field} is already set.',
                        )
                    update_data[field] = request.data[field]
        else:
            update_data = request.data

        serializer = ComplaintUpdateSerializer(complaint, data=update_data, partial=True)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        address_changed = 'address' in request.data or 'pincode' in request.data
        serializer.save()
        if address_changed:
            complaint.latitude = None
            complaint.longitude = None
            complaint.geocode_status = 'not_geocoded'
            complaint.geocode_label = ''
            complaint.geocode_provider = ''
            complaint.geocode_updated_at = None
            complaint.map_radius_m = None
            complaint.save(
                update_fields=[
                    'latitude', 'longitude', 'geocode_status',
                    'geocode_label', 'geocode_provider',
                    'geocode_updated_at', 'map_radius_m',
                ]
            )
        logger.info(f'[COMPLAINT] #{complaint.id} updated by {request.user.email}')
        return self._get_detail_response(complaint, message='Complaint updated.')

    @extend_schema(tags=['complaints'], request=AssignSerializer)
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        complaint = self.get_object()
        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be assigned.',
                'Closed complaints cannot be assigned.',
                status.HTTP_403_FORBIDDEN,
            )

        serializer = AssignSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        engineer = User.objects.filter(
            id=serializer.validated_data['engineer_id'],
            role='engineer',
            is_active=True,
        ).first()
        if engineer is None:
            return error_response('A valid active engineer is required.')

        remark = serializer.validated_data.get('remark') or ''
        old_status = complaint.status
        active_assignment = complaint.get_current_assignment()
        previous_engineer = active_assignment.engineer if active_assignment else None

        if active_assignment is not None:
            active_assignment.unassigned_at = timezone.now()
            active_assignment.unassigned_by = request.user
            active_assignment.save(update_fields=['unassigned_at', 'unassigned_by'])

        ComplaintAssignment.objects.create(
            complaint=complaint,
            engineer=engineer,
            assigned_by=request.user,
        )

        if previous_engineer is not None:
            history_status = old_status
            history_remark = (
                f'Reassigned from {previous_engineer.full_name} '
                f'to {engineer.full_name}. {remark}'
            ).strip()
        else:
            complaint.status = 'assigned'
            complaint.save(update_fields=['status'])
            history_status = 'assigned'
            history_remark = f'Assigned to {engineer.full_name}. {remark}'.strip()

        StatusHistory.objects.create(
            complaint=complaint,
            previous_status=old_status,
            new_status=history_status,
            changed_by=request.user,
            remark=history_remark,
        )

        logger.info(
            f'[COMPLAINT] #{complaint.id} assigned to {engineer.full_name} '
            f'by {request.user.email}'
        )
        return self._get_detail_response(complaint, message='Engineer assigned.')

    @extend_schema(tags=['complaints'], request=StatusUpdateSerializer)
    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        complaint = self.get_object()
        serializer = StatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        new_status = serializer.validated_data['status']
        remark = serializer.validated_data.get('remark')
        current_status = complaint.status

        if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, []):
            return error_response(
                f'Invalid status transition from {current_status} to {new_status}.',
                'status',
            )

        transition = (current_status, new_status)
        if transition in DEDICATED_TRANSITIONS:
            return error_response(
                DEDICATED_TRANSITIONS[transition],
                'This status change must use its dedicated endpoint.',
            )

        if transition in ENGINEER_TRANSITIONS:
            if request.user.role != 'engineer':
                return error_response(
                    'Only the assigned engineer can make this status change.',
                    'Forbidden.',
                    status.HTTP_403_FORBIDDEN,
                )
            if not self._is_currently_assigned_engineer(complaint, request.user):
                return error_response(
                    'You do not have access to this complaint.',
                    'Only the currently assigned engineer can change this status.',
                    status.HTTP_403_FORBIDDEN,
                )
        elif transition in HD_TRANSITIONS:
            if request.user.role not in ['admin', 'helpdesk']:
                return error_response(
                    'Only Admin or Help Desk can make this status change.',
                    'Forbidden.',
                    status.HTTP_403_FORBIDDEN,
                )
        else:
            return error_response(
                f'Invalid status transition from {current_status} to {new_status}.',
                'status',
            )

        if (
            new_status == 'resolved'
            and request.user.role == 'engineer'
            and not complaint.uploads.exists()
        ):
            message = (
                'Upload the signed Service Call Report before marking this '
                'complaint as resolved.'
            )
            return error_response(message, None, status.HTTP_400_BAD_REQUEST)

        complaint.status = new_status
        complaint.save(update_fields=['status'])
        StatusHistory.objects.create(
            complaint=complaint,
            previous_status=current_status,
            new_status=new_status,
            changed_by=request.user,
            remark=remark,
        )

        logger.info(
            f'[COMPLAINT] #{complaint.id} status: {current_status} → {new_status} '
            f'by {request.user.email}'
        )
        return self._get_detail_response(complaint, message='Status updated.')

    @extend_schema(tags=['complaints'], request=JobNoteCreateSerializer, responses={201: JobNoteSerializer})
    @action(detail=True, methods=['post'], url_path='job-note')
    def job_note(self, request, pk=None):
        complaint = self.get_object()

        if request.user.role != 'engineer' or not self._is_currently_assigned_engineer(
            complaint, request.user
        ):
            return error_response(
                'Only the currently assigned engineer can submit a job note.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )

        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be edited.',
                'Closed complaints cannot be edited.',
                status.HTTP_403_FORBIDDEN,
            )

        if complaint.status != 'in_progress':
            return error_response(
                'A job note can only be submitted while the complaint is in progress.'
            )

        if JobNote.objects.filter(complaint=complaint).exists():
            return error_response('A job note already exists for this complaint.')

        serializer = JobNoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        job_note = JobNote.objects.create(
            complaint=complaint,
            text=serializer.validated_data['text'],
            created_by=request.user,
        )

        old_status = complaint.status
        complaint.status = 'parts_requested'
        complaint.save(update_fields=['status'])
        StatusHistory.objects.create(
            complaint=complaint,
            previous_status=old_status,
            new_status='parts_requested',
            changed_by=request.user,
            remark=None,
        )

        logger.info(f'[COMPLAINT] #{complaint.id} job note submitted by {request.user.email}')
        return success_response(
            data=JobNoteSerializer(job_note).data,
            message='Job note submitted. Status updated to Parts Requested.',
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(tags=['complaints'], request=ReopenSerializer)
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        complaint = self.get_object()

        if complaint.status != 'closed':
            return error_response('Only closed complaints can be reopened.')

        serializer = ReopenSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        remark = serializer.validated_data['remark'].strip()
        if not remark:
            return error_response('A remark is required when reopening a complaint.')

        complaint.status = 'resolved'
        complaint.save(update_fields=['status'])
        StatusHistory.objects.create(
            complaint=complaint,
            previous_status='closed',
            new_status='resolved',
            changed_by=request.user,
            remark=remark,
        )

        logger.warning(
            f'[COMPLAINT] #{complaint.id} REOPENED by admin {request.user.email}. '
            f'Reason: {remark}'
        )
        return self._get_detail_response(complaint, message='Complaint reopened.')

    @extend_schema(tags=['complaints'], responses={200: StatusHistorySerializer(many=True)})
    @action(detail=True, methods=['post'])
    def geocode(self, request, pk=None):
        if request.user.role not in ('admin', 'helpdesk'):
            return error_response(
                'Only Admin and Help Desk users can locate complaints.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        complaint = self.get_object()
        if not any(
            (complaint.address, complaint.address_remark, complaint.pincode)
        ):
            return error_response(
                'This complaint has no address, remark, or pincode to locate.'
            )
        try:
            result = geocode_location(
                complaint.address,
                complaint.address_remark,
                complaint.pincode,
            )
        except GeocodeServiceError as exc:
            return error_response(
                str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        complaint.geocode_status = result['status']
        complaint.geocode_label = result['label']
        complaint.geocode_provider = result['provider']
        complaint.latitude = result['latitude']
        complaint.longitude = result['longitude']
        complaint.map_radius_m = result['map_radius_m']
        complaint.geocode_updated_at = timezone.now()
        complaint.save(
            update_fields=[
                'geocode_status', 'geocode_label', 'geocode_provider',
                'latitude', 'longitude', 'map_radius_m', 'geocode_updated_at',
            ]
        )
        return self._get_detail_response(
            complaint,
            message='Approximate location updated.',
        )

    @action(detail=True, methods=['post'], url_path='location')
    def location(self, request, pk=None):
        if request.user.role not in ('admin', 'helpdesk'):
            return error_response(
                'Only Admin and Help Desk users can pin complaint locations.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        complaint = self.get_object()
        serializer = ManualLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)
        complaint.latitude = round(serializer.validated_data['latitude'], 6)
        complaint.longitude = round(serializer.validated_data['longitude'], 6)
        complaint.geocode_status = 'manual'
        complaint.geocode_label = 'Pinned manually by Help Desk'
        complaint.geocode_provider = 'manual'
        complaint.map_radius_m = 50
        complaint.geocode_updated_at = timezone.now()
        complaint.save(
            update_fields=[
                'latitude', 'longitude', 'geocode_status', 'geocode_label',
                'geocode_provider', 'map_radius_m', 'geocode_updated_at',
            ]
        )
        return self._get_detail_response(
            complaint,
            message='Location pin saved.',
        )

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        complaint = self.get_object()
        if not self._can_view(complaint, request.user):
            return error_response(
                'You do not have access to this complaint.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )
        history = complaint.status_history.select_related('changed_by').order_by('changed_at')
        return success_response(data=StatusHistorySerializer(history, many=True).data)

    @extend_schema(tags=['complaints'], responses={200: AssignmentSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def assignments(self, request, pk=None):
        complaint = self.get_object()
        if not self._can_view(complaint, request.user):
            return error_response(
                'You do not have access to this complaint.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )
        assignments = complaint.assignments.select_related(
            'engineer', 'assigned_by', 'unassigned_by'
        ).order_by('-assigned_at')
        return success_response(data=AssignmentSerializer(assignments, many=True).data)

    @extend_schema(tags=['complaints'], responses={200: CommentSerializer(many=True)})
    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        complaint = self.get_object()

        if request.method == 'GET':
            if not self._can_view(complaint, request.user):
                return error_response(
                    'You do not have access to this complaint.',
                    'Forbidden.',
                    status.HTTP_403_FORBIDDEN,
                )
            comments = complaint.comments.select_related('author').order_by('created_at')
            return success_response(data=CommentSerializer(comments, many=True).data)

        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be commented on.',
                'Closed complaints cannot be commented on.',
                status.HTTP_403_FORBIDDEN,
            )

        if request.user.role == 'engineer':
            if not self._is_currently_assigned_engineer(complaint, request.user):
                return error_response(
                    'Only the currently assigned engineer can comment.',
                    'Forbidden.',
                    status.HTTP_403_FORBIDDEN,
                )
        elif request.user.role not in ['admin', 'helpdesk']:
            return error_response('Forbidden.', 'Forbidden.', status.HTTP_403_FORBIDDEN)

        serializer = CommentWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        comment = Comment.objects.create(
            complaint=complaint,
            author=request.user,
            body=serializer.validated_data['body'],
        )
        logger.info(f'[COMPLAINT] #{complaint.id} comment added by {request.user.email}')
        return success_response(
            data=CommentSerializer(comment).data,
            message='Comment added.',
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=['complaints'],
        request=CommentWriteSerializer,
        parameters=[
            OpenApiParameter('comment_id', OpenApiTypes.INT, OpenApiParameter.PATH)
        ],
    )
    @action(
        detail=True,
        methods=['patch'],
        url_path=r'comments/(?P<comment_id>[^/.]+)',
    )
    def edit_comment(self, request, pk=None, comment_id=None):
        complaint = self.get_object()
        try:
            comment_id = int(comment_id)
        except (TypeError, ValueError):
            return error_response(
                'Comment not found.', 'Comment not found.', status.HTTP_404_NOT_FOUND
            )
        comment = Comment.objects.filter(
            id=comment_id, complaint=complaint
        ).select_related('author').first()
        if comment is None:
            return error_response(
                'Comment not found.', 'Comment not found.', status.HTTP_404_NOT_FOUND
            )

        if comment.author_id != request.user.id:
            return error_response(
                'You can only edit your own comments.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )

        latest_comment = complaint.comments.order_by('-created_at').first()
        if latest_comment is None or latest_comment.id != comment.id:
            return error_response(
                'You can only edit your comment if no one has commented after you.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )

        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be edited.',
                'Closed complaints cannot be edited.',
                status.HTTP_403_FORBIDDEN,
            )

        serializer = CommentWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        comment.body = serializer.validated_data['body']
        comment.is_edited = True
        comment.edited_at = timezone.now()
        comment.save(update_fields=['body', 'is_edited', 'edited_at'])

        logger.info(f'[COMPLAINT] #{complaint.id} comment edited by {request.user.email}')
        return success_response(data=CommentSerializer(comment).data, message='Comment updated.')

    @extend_schema(tags=['complaints'])
    @action(detail=True, methods=['get', 'post'], url_path='uploads')
    def uploads(self, request, pk=None):
        complaint = self.get_object()

        if request.method == 'GET':
            if not self._can_view(complaint, request.user):
                return error_response(
                    'You do not have access to this complaint.',
                    'Forbidden.',
                    status.HTTP_403_FORBIDDEN,
                )
            uploads = complaint.uploads.select_related('uploaded_by').order_by(
                '-upload_batch', '-uploaded_at'
            )
            batches = {}
            for upload in uploads:
                batches.setdefault(upload.upload_batch, []).append(upload)

            data = []
            for batch_number in sorted(batches.keys(), reverse=True):
                files = batches[batch_number]
                first = files[0]
                data.append({
                    'batch_number': batch_number,
                    'uploaded_at': first.uploaded_at,
                    'uploaded_by': UserMiniSerializer(first.uploaded_by).data
                    if first.uploaded_by else None,
                    'files': UploadFileSerializer(files, many=True).data,
                })
            return success_response(data=data)

        if request.user.role != 'engineer' or not self._is_currently_assigned_engineer(
            complaint, request.user
        ):
            return error_response(
                'Only the currently assigned engineer can upload files.',
                'Forbidden.',
                status.HTTP_403_FORBIDDEN,
            )

        if complaint.status == 'closed':
            return error_response(
                'Closed complaints cannot be edited.',
                'Closed complaints cannot be edited.',
                status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist('files')
        if not files:
            return error_response(
                'At least one file is required.', {'files': ['No files were provided.']}
            )

        file_types = []
        for upload in files:
            extension = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else ''
            if extension in IMAGE_EXTENSIONS:
                file_types.append('image')
            elif extension == 'pdf':
                file_types.append('pdf')
            else:
                return error_response(
                    f'Unsupported file type: {upload.name}. Only JPG, PNG, and PDF are allowed.'
                )
            if upload.size > MAX_UPLOAD_SIZE:
                return error_response(f'{upload.name} exceeds the 10MB size limit.')

        if len(set(file_types)) > 1:
            return error_response('Images and PDFs cannot be mixed in the same upload.')

        if file_types[0] == 'image' and len(files) > 3:
            return error_response('A maximum of 3 images can be uploaded at once.')

        if file_types[0] == 'pdf' and len(files) > 1:
            return error_response('Only one PDF can be uploaded at a time.')

        last_batch = complaint.uploads.aggregate(max_batch=Max('upload_batch'))['max_batch']
        batch_number = (last_batch or 0) + 1

        created = []
        for upload, file_type in zip(files, file_types):
            created.append(FileUpload.objects.create(
                complaint=complaint,
                file=upload,
                file_type=file_type,
                original_name=upload.name,
                upload_batch=batch_number,
                uploaded_by=request.user,
            ))

        logger.info(
            f'[COMPLAINT] #{complaint.id} — {len(created)} file(s) uploaded '
            f'(batch {batch_number}) by {request.user.email}'
        )
        return success_response(
            data={
                'batch_number': batch_number,
                'files': UploadFileSerializer(created, many=True).data,
            },
            message=f'{len(created)} file(s) uploaded successfully.',
            status_code=status.HTTP_201_CREATED,
        )
