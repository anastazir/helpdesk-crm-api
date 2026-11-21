import logging

from django.db.models import Q
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

from .models import User
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
                'Invalid credentials.', serializer.errors, status.HTTP_401_UNAUTHORIZED
            )

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.check_password(password):
            logger.warning(f'[AUTH] Failed login attempt for: {email}')
            return error_response(
                'Invalid credentials.', 'Invalid email or password.',
                status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            logger.warning(f'[AUTH] Disabled account login attempt: {email}')
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
        queryset = self.get_queryset()

        role = request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1', 'yes'])

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(email__icontains=search)
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
        return success_response(data=UserDetailSerializer(user).data)

    @extend_schema(tags=['users'], request=UserUpdateSerializer, responses={200: UserDetailSerializer})
    def partial_update(self, request, pk=None):
        user = self.get_object()
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)
        serializer.save()
        logger.info(f'[USER] Updated: {user.email} by {request.user.email}')
        return success_response(
            data=UserDetailSerializer(user).data, message='User updated.'
        )

    @extend_schema(tags=['users'], responses={200: None})
    @action(detail=True, methods=['post'])
    def disable(self, request, pk=None):
        user = self.get_object()
        if user.role == 'admin':
            return error_response(
                'Admin accounts cannot be disabled.',
                'Admin accounts cannot be disabled.',
                status.HTTP_403_FORBIDDEN,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])
        logger.warning(f'[USER] Disabled: {user.email} by {request.user.email}')
        return success_response(message='User account disabled.')

    @extend_schema(tags=['users'], responses={200: None})
    @action(detail=True, methods=['post'])
    def enable(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
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
        logger.info(f'[USER] Password reset: {user.email} by {request.user.email}')
        return success_response(message='Password updated.')

    @extend_schema(tags=['users'], responses={200: EngineerSerializer(many=True)})
    @action(detail=False, methods=['get'])
    def engineers(self, request):
        queryset = User.objects.filter(role='engineer', is_active=True).order_by('full_name')

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
        logger.info(
            f'[USER] Zone {zone.name} removed from {user.email} by {request.user.email}'
        )
        return success_response(
            data=ZoneMiniSerializer(user.get_current_zones(), many=True).data,
            message='Zone removed.',
        )
