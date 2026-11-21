from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.zones.models import EngineerZoneAssignment, Zone

from .models import User


class ZoneMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ['id', 'name']


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'role']


class UserSerializer(serializers.ModelSerializer):
    current_zones = serializers.SerializerMethodField()
    active_complaint_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'email', 'phone', 'role', 'is_active',
            'created_at', 'current_zones', 'active_complaint_count',
        ]

    @extend_schema_field(ZoneMiniSerializer(many=True))
    def get_current_zones(self, obj):
        return ZoneMiniSerializer(obj.get_current_zones(), many=True).data

    @extend_schema_field(OpenApiTypes.INT)
    def get_active_complaint_count(self, obj):
        return obj.get_active_complaint_count()


class ZoneHistorySerializer(serializers.ModelSerializer):
    zone = ZoneMiniSerializer(read_only=True)
    changed_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = EngineerZoneAssignment
        fields = ['id', 'zone', 'action', 'changed_at', 'changed_by']


class UserDetailSerializer(UserSerializer):
    zone_history = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['zone_history']

    @extend_schema_field(ZoneHistorySerializer(many=True))
    def get_zone_history(self, obj):
        history = obj.zone_assignment_history.select_related(
            'zone', 'changed_by'
        ).order_by('-changed_at')[:10]
        return ZoneHistorySerializer(history, many=True).data


class EngineerSerializer(serializers.ModelSerializer):
    current_zones = serializers.SerializerMethodField()
    active_complaint_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'current_zones', 'active_complaint_count']

    @extend_schema_field(ZoneMiniSerializer(many=True))
    def get_current_zones(self, obj):
        return ZoneMiniSerializer(obj.get_current_zones(), many=True).data

    @extend_schema_field(OpenApiTypes.INT)
    def get_active_complaint_count(self, obj):
        return obj.get_active_complaint_count()


class LoginUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'role', 'is_active']


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'email', 'phone', 'role', 'is_active', 'created_at',
        ]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    zone_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone', 'password', 'role', 'zone_ids']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        zone_ids = validated_data.pop('zone_ids', [])
        password = validated_data.pop('password')
        request = self.context.get('request')
        if request is not None and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        user = User.objects.create_user(password=password, **validated_data)

        if user.role == 'engineer' and zone_ids:
            zones = Zone.objects.filter(id__in=zone_ids)
            for zone in zones:
                EngineerZoneAssignment.objects.create(
                    engineer=user,
                    zone=zone,
                    action='added',
                    changed_by=request.user if request is not None else None,
                )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['full_name', 'phone']


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)


class UserZoneSerializer(serializers.Serializer):
    zone_id = serializers.IntegerField()
