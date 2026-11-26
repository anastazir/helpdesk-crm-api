from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.users.serializers import UserMiniSerializer

from .models import (
    STATUS_CHOICES,
    Comment,
    Complaint,
    ComplaintAssignment,
    FileUpload,
    IssueType,
    JobNote,
    StatusHistory,
)


class IssueTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueType
        fields = ['id', 'name', 'order']


class IssueTypeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueType
        fields = ['id', 'name']


class ComplaintZoneMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ComplaintListSerializer(serializers.ModelSerializer):
    zone = ComplaintZoneMiniSerializer(read_only=True)
    issues = IssueTypeMiniSerializer(many=True, read_only=True)
    assigned_engineer = serializers.SerializerMethodField()
    created_by = UserMiniSerializer(read_only=True)
    time_open_seconds = serializers.SerializerMethodField()
    time_in_status_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            'id', 'reference', 'caller_name', 'caller_phone', 'zone', 'issues', 'status',
            'assigned_engineer', 'created_by', 'created_at',
            'time_open_seconds', 'time_in_status_seconds',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_assigned_engineer(self, obj):
        engineer = obj.get_assigned_engineer()
        return engineer.full_name if engineer else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_time_open_seconds(self, obj):
        return int(obj.get_time_open_seconds())

    @extend_schema_field(OpenApiTypes.INT)
    def get_time_in_status_seconds(self, obj):
        return int(obj.get_time_in_status_seconds())


class EngineerLimitedComplaintSerializer(serializers.ModelSerializer):
    zone = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = ['id', 'reference', 'zone', 'address', 'status', 'created_at']

    @extend_schema_field(OpenApiTypes.STR)
    def get_zone(self, obj):
        return obj.zone.name if obj.zone else None


class JobNoteSerializer(serializers.ModelSerializer):
    created_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = JobNote
        fields = ['id', 'text', 'created_at', 'created_by']


class ComplaintDetailSerializer(serializers.ModelSerializer):
    zone = ComplaintZoneMiniSerializer(read_only=True)
    issues = IssueTypeMiniSerializer(many=True, read_only=True)
    created_by = UserMiniSerializer(read_only=True)
    assigned_engineer = serializers.SerializerMethodField()
    job_note = serializers.SerializerMethodField()
    whatsapp_notification = serializers.SerializerMethodField()
    time_open_seconds = serializers.SerializerMethodField()
    time_in_status_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            'id', 'reference', 'caller_phone', 'caller_name', 'bmid', 'aadhaar', 'zone',
            'department', 'designation', 'address', 'address_remark', 'pincode',
            'cpu_serial', 'monitor_serial', 'issues', 'others_description',
            'status', 'latitude', 'longitude', 'geocode_status',
            'geocode_label', 'geocode_provider', 'geocode_updated_at',
            'map_radius_m',
            'created_at', 'created_by', 'assigned_engineer', 'job_note',
            'whatsapp_notification', 'time_open_seconds',
            'time_in_status_seconds',
        ]

    @extend_schema_field(UserMiniSerializer)
    def get_assigned_engineer(self, obj):
        engineer = obj.get_assigned_engineer()
        return UserMiniSerializer(engineer).data if engineer else None

    @extend_schema_field(JobNoteSerializer)
    def get_job_note(self, obj):
        try:
            job_note = obj.job_note
        except JobNote.DoesNotExist:
            return None
        return JobNoteSerializer(job_note).data

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_whatsapp_notification(self, obj):
        from apps.whatsapp.models import whatsapp_feature_enabled

        if not whatsapp_feature_enabled():
            return None
        notification = (
            obj.whatsapp_notifications
            .order_by('-queued_at')
            .first()
        )
        if notification is None:
            return None
        return {
            'id': notification.id,
            'status': notification.status,
            'sent_at': notification.sent_at,
            'delivered_at': notification.delivered_at,
            'read_at': notification.read_at,
            'failed_at': notification.failed_at,
            'last_error': notification.last_error,
        }

    @extend_schema_field(OpenApiTypes.INT)
    def get_time_open_seconds(self, obj):
        return int(obj.get_time_open_seconds())

    @extend_schema_field(OpenApiTypes.INT)
    def get_time_in_status_seconds(self, obj):
        return int(obj.get_time_in_status_seconds())


class ComplaintCreateSerializer(serializers.Serializer):
    caller_phone = serializers.CharField(max_length=20)
    caller_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    bmid = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    aadhaar = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    zone_id = serializers.IntegerField(required=False, allow_null=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    designation = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address_remark = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True
    )
    pincode = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    geocode_status = serializers.ChoiceField(
        choices=['not_geocoded', 'address', 'landmark', 'pincode', 'manual', 'not_found', 'failed'],
        required=False,
        default='not_geocoded',
    )
    geocode_label = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True
    )
    geocode_provider = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True
    )
    map_radius_m = serializers.IntegerField(required=False, allow_null=True)
    cpu_serial = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    monitor_serial = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    issue_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, write_only=True
    )
    others_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_issue_ids(self, value):
        unique_ids = set(value)
        issues = list(IssueType.objects.filter(id__in=unique_ids))
        if len(issues) != len(unique_ids):
            raise serializers.ValidationError('One or more issue IDs are invalid.')
        return list(unique_ids)

    def validate(self, attrs):
        issue_ids = attrs.get('issue_ids') or []
        if not issue_ids:
            raise serializers.ValidationError(
                {'issue_ids': ['At least one issue must be selected.']}
            )

        others_selected = IssueType.objects.filter(
            id__in=issue_ids, name__iexact='Others'
        ).exists()
        if others_selected and not (attrs.get('others_description') or '').strip():
            raise serializers.ValidationError(
                {'others_description': ['This field is required when "Others" is selected.']}
            )

        zone_id = attrs.get('zone_id')
        if zone_id is not None:
            from apps.zones.models import Zone

            if not Zone.objects.filter(id=zone_id).exists():
                raise serializers.ValidationError({'zone_id': ['Zone not found.']})

        return attrs


class ComplaintUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = [
            'caller_name', 'caller_phone', 'department', 'designation',
            'address', 'address_remark', 'pincode', 'cpu_serial', 'monitor_serial',
        ]


class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=STATUS_CHOICES)
    remark = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AssignSerializer(serializers.Serializer):
    engineer_id = serializers.IntegerField()
    remark = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class JobNoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField()


class ReopenSerializer(serializers.Serializer):
    remark = serializers.CharField()


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = StatusHistory
        fields = ['id', 'previous_status', 'new_status', 'changed_at', 'changed_by', 'remark']


class AssignmentSerializer(serializers.ModelSerializer):
    engineer = UserMiniSerializer(read_only=True)
    assigned_by = UserMiniSerializer(read_only=True)
    unassigned_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = ComplaintAssignment
        fields = [
            'id', 'engineer', 'assigned_at', 'assigned_by',
            'unassigned_at', 'unassigned_by',
        ]


class CommentSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author', 'body', 'created_at', 'edited_at', 'is_edited']


class CommentWriteSerializer(serializers.Serializer):
    body = serializers.CharField()


class UploadFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = ['id', 'file_url', 'file_type', 'original_name']

    def get_file_url(self, obj):
        return obj.file.url if obj.file else None


class ManualLocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
