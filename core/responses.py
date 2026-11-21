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


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler output in the standard response format.
    """
    response = exception_handler(exc, context)
    if response is not None:
        logger.warning(f'[EXCEPTION] {exc.__class__.__name__}: {exc}')
        response.data = {
            'success': False,
            'message': 'An error occurred.',
            'data': None,
            'errors': response.data,
        }
    return response
