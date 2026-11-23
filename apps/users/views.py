import logging

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.zones.models import EngineerZoneAssignment, Zone
from core.pagination import StandardPagination
from core.permissions import IsAdmin
from core.responses import error_response, success_response

from .audit import log_user_event
from .models import User, UserAuditLog
from .serializers import (
    EngineerSerializer,
    LoginSerializer,
    LoginUserSerializer,
    MeSerializer,
    ResetPasswordSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserSerializer,
    UserUpdateSerializer,
    UserZoneSerializer,
    UserAuditLogSerializer,
    ZoneHistorySerializer,
    ZoneMiniSerializer,
)

logger = logging.getLogger('apps.users')


@extend_schema(tags=['auth'])
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        request=LoginSerializer,
        responses={200: LoginUserSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning('[AUTH] Failed login attempt with invalid payload')
            return error_response(
                'Enter a valid email or phone number.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        identifier = serializer.validated_data['identifier']
        password = serializer.validated_data['password']

        if '@' in identifier:
            user = User.objects.filter(
                email__iexact=identifier, is_deleted=False
            ).first()
        else:
            user = User.objects.filter(
                phone=identifier, is_deleted=False
            ).first()
        if user is None or not user.check_password(password):
            logger.warning(f'[AUTH] Failed login attempt for: {identifier}')
            return error_response(
                'Invalid credentials.', 'Invalid email or password.',
                status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active or user.is_deleted:
            logger.warning(f'[AUTH] Disabled account login attempt: {identifier}')
            return error_response(
                'Your account has been disabled. Contact your administrator.',
                'Your account has been disabled. Contact your administrator.',
                status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        logger.info(f'[AUTH] Login: {user.email}')
        return success_response(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': LoginUserSerializer(user).data,
            },
            message='Login successful.',
        )


@extend_schema(tags=['auth'])
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['auth'], request=None, responses={200: None})
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return error_response(
                'Refresh token is required.', 'Refresh token is required.'
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            logger.warning(f'[AUTH] Failed logout for: {request.user.email}')
            return error_response('Invalid or expired refresh token.')

        logger.info(f'[AUTH] Logout: {request.user.email}')
        return success_response(message='Logged out successfully.')


@extend_schema(tags=['auth'])
class TokenRefreshAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        request=TokenRefreshSerializer,
        responses={200: TokenRefreshSerializer},
    )
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            logger.warning(f'[AUTH] Failed token refresh: {exc}')
            return error_response(
                'Invalid or expired refresh token.',
                str(exc),
                status.HTTP_401_UNAUTHORIZED,
            )
        return success_response(data=serializer.validated_data)


@extend_schema(tags=['auth'])
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['auth'], responses={200: MeSerializer})
    def get(self, request):
        return success_response(data=MeSerializer(request.user).data)


@extend_schema(tags=['users'])
class UserViewSet(viewsets.GenericViewSet):
    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer
    pagination_class = StandardPagination

    def get_permissions(self):
        if self.action == 'engineers':
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action == 'partial_update':
            return UserUpdateSerializer
        if self.action == 'retrieve':
            return UserDetailSerializer
        if self.action == 'engineers':
            return EngineerSerializer
        return UserSerializer

    @extend_schema(tags=['users'], responses={200: UserSerializer(many=True)})
    def list(self, request):
        queryset = self.get_queryset().filter(is_deleted=False)

        role_values = []
        for raw in request.query_params.getlist('role'):
            role_values.extend(
                part.strip() for part in raw.split(',') if part.strip()
            )
        if role_values:
            queryset = queryset.filter(role__in=role_values)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1', 'yes'])

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        serializer = UserSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(tags=['users'], request=UserCreateSerializer, responses={201: UserSerializer})
    def create(self, request):
        serializer = UserCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        user = serializer.save()
        log_user_event(action='created', actor=request.user, target=user, changes={'created': {'old': None, 'new': user.role}})
        logger.info(
            f'[USER] Created: {user.email} ({user.role}) by {request.user.email}'
        )
        return success_response(
            data=UserSerializer(user).data,
            message='User created successfully.',
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(tags=['users'], responses={200: UserDetailSerializer})
    def retrieve(self, request, pk=None):
        user = self.get_object()
        if user.is_deleted:
            return error_response('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        return success_response(data=UserDetailSerializer(user).data)

    @extend_schema(tags=['users'], request=UserUpdateSerializer, responses={200: UserDetailSerializer})
    def partial_update(self, request, pk=None):
        user = self.get_object()
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)
        old_values = {field: getattr(user, field) for field in ['full_name', 'email', 'phone']}
        serializer.save()
        changes = {}
        for field in ['full_name', 'email', 'phone']:
            old = old_values[field]
            new = getattr(user, field)
            if old != new:
                changes[field] = {'old': old, 'new': new}
        if changes:
            log_user_event(action='updated', actor=request.user, target=user, changes=changes)
        logger.info(f'[USER] Updated: {user.email} by {request.user.email}')
        return success_response(
            data=UserDetailSerializer(user).data, message='User updated.'
        )

    @extend_schema(tags=['users'], responses={200: None})
    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        user = self.get_object()
        if user.is_deleted:
            return error_response('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        if user.id == request.user.id:
            return error_response('You cannot disable your own account.', status_code=status.HTTP_403_FORBIDDEN)
        if user.role == 'admin' and not User.objects.filter(
            role='admin', is_active=True, is_deleted=False
        ).exclude(pk=user.pk).exists():
            return error_response(
                'The last active Admin cannot be disabled.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])
        log_user_event(action='disabled', actor=request.user, target=user)
        logger.warning(f'[USER] Disabled: {user.email} by {request.user.email}')
        return success_response(message='User account disabled.')

    @extend_schema(tags=['users'], responses={200: None})
    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        user = self.get_object()
        if user.is_deleted:
            return error_response('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        user.is_active = True
        user.save(update_fields=['is_active'])
        log_user_event(action='enabled', actor=request.user, target=user)
        logger.info(f'[USER] Enabled: {user.email} by {request.user.email}')
        return success_response(message='User account enabled.')

    @extend_schema(tags=['users'], request=ResetPasswordSerializer, responses={200: None})
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        if user.role == 'admin' and user.id != request.user.id:
            return error_response(
                "Another admin's password cannot be changed.",
                'Admin passwords can only be changed by their owner.',
                status.HTTP_403_FORBIDDEN,
            )

        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        log_user_event(action='password_changed', actor=request.user, target=user)
        logger.info(f'[USER] Password reset: {user.email} by {request.user.email}')
        return success_response(message='Password updated.')

    @extend_schema(tags=['users'], responses={200: UserAuditLogSerializer(many=True)})
    @action(detail=False, methods=['get'], url_path='audit-logs')
    def audit_logs(self, request):
        queryset = UserAuditLog.objects.all().order_by('-created_at', '-id')
        action_value = request.query_params.get('action')
        if action_value:
            queryset = queryset.filter(action=action_value)
        actor_id = request.query_params.get('actor')
        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)
        target_id = request.query_params.get('target')
        if target_id:
            queryset = queryset.filter(target_id=target_id)
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(target_name__icontains=search)
                | Q(target_email__icontains=search)
                | Q(target_phone__icontains=search)
            )
        date_from = request.query_params.get('date_from')
        if date_from:
            parsed = parse_date(date_from)
            if parsed:
                queryset = queryset.filter(created_at__date__gte=parsed)
        date_to = request.query_params.get('date_to')
        if date_to:
            parsed = parse_date(date_to)
            if parsed:
                queryset = queryset.filter(created_at__date__lte=parsed)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(
            UserAuditLogSerializer(page, many=True).data
        )

    def destroy(self, request, pk=None):
        user = self.get_object()
        if user.is_deleted:
            return error_response('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        if user.id == request.user.id:
            return error_response('You cannot delete your own account.', status_code=status.HTTP_403_FORBIDDEN)
        active_assignments = user.complaint_assignments.filter(
            unassigned_at__isnull=True,
        ).exclude(complaint__status='closed')
        if active_assignments.exists():
            refs = list(
                active_assignments.values_list('complaint__reference', flat=True)
            )
            return error_response(
                'Reassign active complaints before deleting this user.',
                {'active_complaints': refs},
                status.HTTP_409_CONFLICT,
            )
        if user.role == 'admin' and not User.objects.filter(
            role='admin', is_active=True, is_deleted=False
        ).exclude(pk=user.pk).exists():
            return error_response(
                'The last active Admin cannot be deleted.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        log_user_event(action='deleted', actor=request.user, target=user)
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = timezone.now()
        user.deleted_by = request.user
        user.save(update_fields=['is_deleted', 'is_active', 'deleted_at', 'deleted_by'])
        logger.warning(f'[USER] Deleted: {user.email} by {request.user.email}')
        return success_response(message='User deleted.')

    @extend_schema(tags=['users'], responses={200: EngineerSerializer(many=True)})
    @action(detail=False, methods=['get'])
    def engineers(self, request):
        queryset = User.objects.filter(
            role='engineer', is_active=True, is_deleted=False
        ).order_by('full_name')

        zone_id = request.query_params.get('zone_id')
        if zone_id:
            try:
                zone_id = int(zone_id)
            except (TypeError, ValueError):
                return error_response('Invalid zone_id.', 'zone_id must be an integer.')
            queryset = [user for user in queryset if zone_id in user.get_current_zone_ids()]

        return success_response(data=EngineerSerializer(queryset, many=True).data)

    @extend_schema(tags=['users'], responses={200: ZoneHistorySerializer(many=True)})
    @action(detail=True, methods=['get'], url_path='zone-history')
    def zone_history(self, request, pk=None):
        user = self.get_object()
        history = user.zone_assignment_history.select_related(
            'zone', 'changed_by'
        ).order_by('-changed_at')
        return success_response(data=ZoneHistorySerializer(history, many=True).data)

    @extend_schema(tags=['users'], request=UserZoneSerializer, responses={200: ZoneMiniSerializer(many=True)})
    @action(detail=True, methods=['post'], url_path='zones')
    def assign_zone(self, request, pk=None):
        user = self.get_object()
        if user.role != 'engineer':
            return error_response('Zones can only be assigned to engineers.')

        serializer = UserZoneSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        zone_id = serializer.validated_data['zone_id']
        zone = Zone.objects.filter(id=zone_id).first()
        if zone is None:
            return error_response('Zone not found.')

        if zone_id in user.get_current_zone_ids():
            return error_response('Engineer is already assigned to this zone.')

        EngineerZoneAssignment.objects.create(
            engineer=user,
            zone=zone,
            action='added',
            changed_by=request.user,
        )
        log_user_event(
            action='zone_added', actor=request.user, target=user,
            changes={'zone': {'old': None, 'new': zone.name}},
        )
        logger.info(
            f'[USER] Zone {zone.name} assigned to {user.email} by {request.user.email}'
        )
        return success_response(
            data=ZoneMiniSerializer(user.get_current_zones(), many=True).data,
            message='Zone assigned.',
        )

    @extend_schema(
        tags=['users'],
        responses={200: ZoneMiniSerializer(many=True)},
        parameters=[
            OpenApiParameter('zone_id', OpenApiTypes.INT, OpenApiParameter.PATH)
        ],
    )
    @action(detail=True, methods=['delete'], url_path=r'zones/(?P<zone_id>[^/.]+)')
    def remove_zone(self, request, pk=None, zone_id=None):
        user = self.get_object()
        if user.role != 'engineer':
            return error_response('Zones can only be assigned to engineers.')

        try:
            zone_id = int(zone_id)
        except (TypeError, ValueError):
            return error_response('Invalid zone_id.', 'zone_id must be an integer.')

        if zone_id not in user.get_current_zone_ids():
            return error_response('Engineer is not assigned to this zone.')

        zone = Zone.objects.filter(id=zone_id).first()
        if zone is None:
            return error_response('Zone not found.')

        EngineerZoneAssignment.objects.create(
            engineer=user,
            zone=zone,
            action='removed',
            changed_by=request.user,
        )
        log_user_event(
            action='zone_removed', actor=request.user, target=user,
            changes={'zone': {'old': zone.name, 'new': None}},
        )
        logger.info(
            f'[USER] Zone {zone.name} removed from {user.email} by {request.user.email}'
        )
        return success_response(
            data=ZoneMiniSerializer(user.get_current_zones(), many=True).data,
            message='Zone removed.',
        )
