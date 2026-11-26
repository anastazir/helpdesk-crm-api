import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.users.audit import log_user_event
from core.permissions import IsAdmin
from core.responses import error_response, success_response

from .models import (
    WhatsAppSettings,
    whatsapp_configured,
    whatsapp_feature_enabled,
)
from .serializers import WhatsAppMeUpdateSerializer, WhatsAppSettingsSerializer

logger = logging.getLogger('apps.whatsapp')


def _server_enabled():
    return bool(settings.USE_WHATSAPP and settings.WHATSAPP_ENABLED)


class WhatsAppSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        row = WhatsAppSettings.load()
        return success_response(
            {
                'use_whatsapp': row.use_whatsapp,
                'stored_use_whatsapp': row.use_whatsapp,
                'enabled': whatsapp_feature_enabled(),
                'server_enabled': _server_enabled(),
                'configured': whatsapp_configured(),
                'can_manage': True,
            }
        )

    def patch(self, request):
        serializer = WhatsAppSettingsSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the WhatsApp setting.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        row = WhatsAppSettings.load()
        row.use_whatsapp = serializer.validated_data['use_whatsapp']
        row.updated_by = request.user
        row.save(update_fields=['use_whatsapp', 'updated_by', 'updated_at'])
        logger.info(
            '[WHATSAPP SETTINGS] user=%s use_whatsapp=%s',
            request.user.id,
            row.use_whatsapp,
        )
        return success_response(
            {
                'use_whatsapp': row.use_whatsapp,
                'stored_use_whatsapp': row.use_whatsapp,
                'enabled': whatsapp_feature_enabled(),
                'server_enabled': _server_enabled(),
                'configured': whatsapp_configured(),
                'can_manage': True,
            }
        )


class WhatsAppMeView(APIView):
    permission_classes = [IsAuthenticated]

    def _payload(self, user):
        row = WhatsAppSettings.load()
        return {
            'use_whatsapp': row.use_whatsapp,
            'enabled': whatsapp_feature_enabled(),
            'server_enabled': _server_enabled(),
            'configured': whatsapp_configured(),
            'phone': user.phone,
            'can_opt_in': bool(user.phone),
            'whatsapp_opt_in': user.whatsapp_opt_in,
            'whatsapp_opt_in_at': user.whatsapp_opt_in_at,
            'whatsapp_opt_out_at': user.whatsapp_opt_out_at,
            'whatsapp_opt_in_source': user.whatsapp_opt_in_source,
        }

    def get(self, request):
        return success_response(self._payload(request.user))

    def patch(self, request):
        serializer = WhatsAppMeUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'Please check the WhatsApp setting.',
                serializer.errors,
                status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        opt_in = serializer.validated_data['whatsapp_opt_in']
        if opt_in and not user.phone:
            return error_response(
                'Add a phone number before enabling WhatsApp notifications.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        old_value = user.whatsapp_opt_in
        now = timezone.now()
        user.whatsapp_opt_in = opt_in
        if opt_in:
            user.whatsapp_opt_in_at = now
            user.whatsapp_opt_out_at = None
        else:
            user.whatsapp_opt_out_at = now
        user.whatsapp_opt_in_source = 'self_service'
        user.save(
            update_fields=[
                'whatsapp_opt_in',
                'whatsapp_opt_in_at',
                'whatsapp_opt_out_at',
                'whatsapp_opt_in_source',
            ]
        )
        log_user_event(
            action='updated',
            actor=user,
            target=user,
            changes={
                'whatsapp_opt_in': {
                    'old': old_value,
                    'new': opt_in,
                }
            },
            note='WhatsApp consent changed by user.',
            source='self_service',
        )
        logger.info(
            '[WHATSAPP] user=%s opted %s',
            user.id,
            'in' if opt_in else 'out',
        )
        return success_response(self._payload(user))
