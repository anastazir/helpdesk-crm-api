from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Zone


class ZoneSerializer(serializers.ModelSerializer):
    engineer_count = serializers.SerializerMethodField()
    complaint_count = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = ['id', 'name', 'is_active', 'engineer_count', 'complaint_count']
        read_only_fields = ['id', 'engineer_count', 'complaint_count']

    @extend_schema_field(OpenApiTypes.INT)
    def get_engineer_count(self, obj):
        return obj.get_engineer_count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_complaint_count(self, obj):
        return obj.get_complaint_count()
