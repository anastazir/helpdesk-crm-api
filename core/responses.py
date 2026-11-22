import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger('core')


def success_response(data=None, message='', status_code=status.HTTP_200_OK):
    logger.debug(f'[RESPONSE] success=True | status={status_code} | message={message}')
    return Response({
        'success': True,
        'message': message,
        'data': data,
        'errors': None,
    }, status=status_code)


def error_response(message='An error occurred', errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    logger.warning(f'[RESPONSE] success=False | status={status_code} | message={message}')
    return Response({
        'success': False,
        'message': message,
        'data': None,
        'errors': errors,
    }, status=status_code)


def _extract_message(detail):
    if isinstance(detail, str):
        message = detail.strip()
        return message or None

    if isinstance(detail, (list, tuple)):
        for item in detail:
            message = _extract_message(item)
            if message:
                return message
        return None

    if isinstance(detail, dict):
        for key in ('detail', 'message', 'error', 'non_field_errors'):
            if key in detail:
                message = _extract_message(detail[key])
                if message:
                    return message
        for value in detail.values():
            message = _extract_message(value)
            if message:
                return message

    return None


def _fallback_message(status_code):
    if status_code == status.HTTP_400_BAD_REQUEST:
        return 'The request could not be processed. Please check the submitted data.'
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return 'Authentication is required. Please sign in again.'
    if status_code == status.HTTP_403_FORBIDDEN:
        return 'You do not have permission to perform this action.'
    if status_code == status.HTTP_404_NOT_FOUND:
        return 'The requested resource was not found.'
    if status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        return 'This action is not allowed.'
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return 'Too many requests. Please try again later.'
    if status_code >= 500:
        return 'The server ran into a problem. Please try again.'
    return 'The request failed. Please try again.'


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler output in the standard response
    format and preserves a human-readable error message for the frontend.
    """
    response = exception_handler(exc, context)

    if response is None:
        logger.error(
            f'[EXCEPTION] Unhandled {exc.__class__.__name__}: {exc}',
            exc_info=exc,
        )
        return Response({
            'success': False,
            'message': _fallback_message(status.HTTP_500_INTERNAL_SERVER_ERROR),
            'data': None,
            'errors': None,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    message = _extract_message(response.data) or _fallback_message(
        response.status_code
    )
    logger.warning(
        f'[EXCEPTION] {exc.__class__.__name__} | '
        f'status={response.status_code} | {message}'
    )
    response.data = {
        'success': False,
        'message': message,
        'data': None,
        'errors': response.data,
    }
    return response
