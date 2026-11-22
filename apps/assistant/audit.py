import logging

from .models import AIRequestLog

logger = logging.getLogger('apps.assistant')


def log_ai_request(
    *,
    user,
    feature,
    status,
    request_text='',
    response_text='',
    result=None,
    error_message='',
    metadata=None,
):
    usage = (result or {}).get('usage') or {}
    try:
        return AIRequestLog.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            feature=feature,
            status=status,
            request_text=request_text or '',
            response_text=response_text or '',
            metadata=metadata or {},
            model=(result or {}).get('model') or '',
            provider=(result or {}).get('provider') or '',
            prompt_tokens=usage.get('prompt_tokens') or 0,
            completion_tokens=usage.get('completion_tokens') or 0,
            total_tokens=usage.get('total_tokens') or 0,
            cost_usd=usage.get('cost'),
            cost_inr=usage.get('cost_inr'),
            latency_ms=(result or {}).get('latency_ms') or 0,
            tools_used=(result or {}).get('tools_used') or [],
            error_message=error_message or '',
        )
    except Exception:
        logger.exception('[AI LOG] Could not persist AI request log.')
        return None
