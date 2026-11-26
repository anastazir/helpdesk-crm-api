from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.zones.models import EngineerZoneAssignment, Zone

from .models import User, UserAuditLog
from .phone import InvalidPhoneError, normalize_phone


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
            'whatsapp_opt_in', 'whatsapp_opt_in_at', 'whatsapp_opt_out_at',
            'whatsapp_opt_in_source', 'created_at', 'current_zones',
            'active_complaint_count',
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
    identifier = serializers.CharField(required=False, allow_blank=False)
    email = serializers.EmailField(required=False, allow_blank=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = (attrs.get('identifier') or attrs.get('email') or '').strip()
        if not identifier:
            raise serializers.ValidationError(
                {'identifier': ['Enter your email or phone number.']}
            )
        if '@' in identifier:
            email_field = serializers.EmailField()
            try:
                email_field.run_validation(identifier)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({'identifier': exc.detail})
        else:
            try:
                identifier = normalize_phone(identifier)
            except InvalidPhoneError as exc:
                raise serializers.ValidationError({'identifier': [str(exc)]})
        attrs['identifier'] = identifier
        return attrs


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    zone_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )
    whatsapp_opt_in = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = User
        fields = [
            'full_name', 'email', 'phone', 'password', 'role',
            'zone_ids', 'whatsapp_opt_in',
        ]

    def validate_role(self, value):
        if value == 'admin':
            raise serializers.ValidationError(
                'Admin users can only be created from the backend.'
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_phone(self, value):
        try:
            normalized = normalize_phone(value)
        except InvalidPhoneError as exc:
            raise serializers.ValidationError(str(exc))
        if User.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError('A user with this phone already exists.')
        return normalized

    def create(self, validated_data):
        zone_ids = validated_data.pop('zone_ids', [])
        password = validated_data.pop('password')
        if validated_data.get('whatsapp_opt_in'):
            validated_data['whatsapp_opt_in_at'] = timezone.now()
            validated_data['whatsapp_opt_in_source'] = 'admin_form'
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
        fields = ['full_name', 'email', 'phone', 'whatsapp_opt_in']

    def update(self, instance, validated_data):
        phone_changed = (
            'phone' in validated_data
            and validated_data['phone'] != instance.phone
        )
        if phone_changed and 'whatsapp_opt_in' not in validated_data:
            validated_data['whatsapp_opt_in'] = False
            validated_data['whatsapp_opt_out_at'] = timezone.now()
            validated_data['whatsapp_opt_in_source'] = 'phone_changed'

        opt_in = validated_data.get('whatsapp_opt_in', None)
        if opt_in is not None and opt_in != instance.whatsapp_opt_in:
            if opt_in:
                validated_data['whatsapp_opt_in_at'] = timezone.now()
                validated_data['whatsapp_opt_out_at'] = None
                validated_data['whatsapp_opt_in_source'] = 'admin_form'
            else:
                validated_data['whatsapp_opt_out_at'] = timezone.now()
                validated_data['whatsapp_opt_in_source'] = 'admin_form'
        return super().update(instance, validated_data)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_phone(self, value):
        try:
            normalized = normalize_phone(value)
        except InvalidPhoneError as exc:
            raise serializers.ValidationError(str(exc))
        if User.objects.filter(phone=normalized).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('A user with this phone already exists.')
        return normalized


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)


class UserZoneSerializer(serializers.Serializer):
    zone_id = serializers.IntegerField()


class UserAuditLogSerializer(serializers.ModelSerializer):
    actor_id = serializers.IntegerField(read_only=True)
    target_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserAuditLog
        fields = [
            'id', 'action', 'actor_id', 'actor_name', 'actor_email', 'actor_role',
            'target_id', 'target_name', 'target_email', 'target_phone',
            'target_role', 'changes', 'note', 'source', 'created_at',
        ]
