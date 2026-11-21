import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.users.serializers import EngineerSerializer
from core.permissions import IsAdmin
from core.responses import error_response, success_response

from .models import Zone
from .serializers import ZoneSerializer

logger = logging.getLogger('apps.zones')


@extend_schema(tags=['zones'])
class ZoneViewSet(viewsets.GenericViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_permissions(self):
        if self.action in ['create', 'partial_update']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    @extend_schema(tags=['zones'], responses={200: ZoneSerializer(many=True)})
    def list(self, request):
        zones = self.get_queryset()
        return success_response(data=ZoneSerializer(zones, many=True).data)

    @extend_schema(tags=['zones'], request=ZoneSerializer, responses={201: ZoneSerializer})
    def create(self, request):
        serializer = ZoneSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        zone = serializer.save(created_by=request.user)
        logger.info(f'[ZONE] Created: {zone.name} by {request.user.email}')
        return success_response(
            data=ZoneSerializer(zone).data,
            message='Zone created successfully.',
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(tags=['zones'], request=ZoneSerializer, responses={200: ZoneSerializer})
    def partial_update(self, request, pk=None):
        zone = self.get_object()
        serializer = ZoneSerializer(zone, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('Validation failed.', serializer.errors)

        zone = serializer.save()
        logger.info(f'[ZONE] Updated: {zone.name} by {request.user.email}')
        return success_response(data=ZoneSerializer(zone).data, message='Zone updated.')

    @extend_schema(tags=['zones'], responses={200: EngineerSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def engineers(self, request, pk=None):
        zone = self.get_object()
        engineers = zone.get_current_engineers()
        return success_response(data=EngineerSerializer(engineers, many=True).data)
