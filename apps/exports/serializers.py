from rest_framework import serializers

from apps.complaints.models import STATUS_CHOICES

COLUMN_HEADERS = {
    'id': 'Complaint ID',
    'caller_name': 'Caller Name',
    'caller_phone': 'Phone',
    'zone': 'Zone',
    'issues': 'Issue(s)',
    'status': 'Status',
    'assigned_engineer': 'Assigned Engineer',
    'cpu_serial': 'CPU Serial No',
    'monitor_serial': 'Monitor Serial No',
    'created_at': 'Created At',
    'time_open': 'Time Open',
    'department': 'Department',
    'designation': 'Designation',
    'bmid': 'BMID',
    'address': 'Address',
    'pincode': 'Pincode',
}

COLUMN_CHOICES = [(key, key) for key in COLUMN_HEADERS]


class ExportFiltersSerializer(serializers.Serializer):
    zone_id = serializers.IntegerField(required=False, allow_null=True)
    zone_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    status = serializers.ChoiceField(
        choices=STATUS_CHOICES, required=False, allow_null=True
    )
    statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=STATUS_CHOICES),
        required=False,
        allow_empty=True,
    )
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    assigned_engineer_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_engineer_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    cpu_serial_contains = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )

    def validate(self, attrs):
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError('date_from cannot be after date_to.')
        return attrs


class ExportPreviewSerializer(serializers.Serializer):
    columns = serializers.ListField(
        child=serializers.ChoiceField(choices=COLUMN_CHOICES),
        required=False,
        allow_empty=True,
    )
    filters = ExportFiltersSerializer(required=False)
    deduplicate = serializers.BooleanField(required=False, default=False)


class ExportDownloadSerializer(serializers.Serializer):
    columns = serializers.ListField(
        child=serializers.ChoiceField(choices=COLUMN_CHOICES),
        allow_empty=False,
    )
    column_order = serializers.ListField(
        child=serializers.ChoiceField(choices=COLUMN_CHOICES),
        required=False,
        allow_empty=False,
    )
    filters = ExportFiltersSerializer(required=False)
    deduplicate = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        column_order = attrs.get('column_order')
        columns = attrs.get('columns')
        if column_order:
            invalid = [key for key in column_order if key not in columns]
            if invalid:
                raise serializers.ValidationError({
                    'column_order': [
                        'Every value in column_order must also be present in columns.'
                    ]
                })
        attrs['effective_columns'] = column_order or columns
        return attrs


class UserAuditExportFiltersSerializer(serializers.Serializer):
    action = serializers.CharField(required=False, allow_blank=True)
    actor_id = serializers.IntegerField(required=False, allow_null=True)
    target_id = serializers.IntegerField(required=False, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError('date_from cannot be after date_to.')
        return attrs


class UserAuditExportSerializer(serializers.Serializer):
    filters = UserAuditExportFiltersSerializer(required=False)
