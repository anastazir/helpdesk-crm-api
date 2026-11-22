import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import error_response, success_response

from .services import (
    BriefingConfigurationError,
    BriefingUpstreamError,
    build_briefing_context,
    generate_briefing,
)

logger = logging.getLogger('apps.assistant')


class DailyBriefingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ('admin', 'helpdesk'):
            return error_response(
                'Only Admin and Help Desk users can generate the AI briefing.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not settings.AI_BRIEFING_ENABLED:
            return error_response(
                'AI briefing is disabled.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        lock_key = f'ai-briefing-lock:{request.user.id}'
        if not cache.add(lock_key, True, timeout=20):
            return error_response(
                'A briefing is already being generated. Please wait a moment.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            context = build_briefing_context()
            result = generate_briefing(context)
            logger.info(
                '[AI BRIEFING] user=%s cost=%s tokens=%s latency_ms=%s',
                request.user.id,
                (result.get('usage') or {}).get('cost'),
                (result.get('usage') or {}).get('total_tokens'),
                result.get('latency_ms'),
            )
            return success_response(
                result,
                message='Daily briefing generated.',
            )
        except BriefingConfigurationError:
            return error_response(
                'AI briefing is not configured on this server.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except BriefingUpstreamError as exc:
            logger.warning('[AI BRIEFING] Upstream failure: %s', exc)
            return error_response(
                str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('[AI BRIEFING] Unexpected failure')
            return error_response(
                'The briefing could not be generated. Please try again.',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            cache.delete(lock_key)
