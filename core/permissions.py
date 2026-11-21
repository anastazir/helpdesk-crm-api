import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger('core')


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        allowed = request.user.is_authenticated and request.user.role == 'admin'
        if not allowed:
            logger.warning(
                f'[PERMISSION] IsAdmin denied for user {request.user} '
                f'on {view.__class__.__name__}'
            )
        return allowed


class IsAdminOrHD(BasePermission):
    def has_permission(self, request, view):
        allowed = request.user.is_authenticated and request.user.role in ['admin', 'helpdesk']
        if not allowed:
            logger.warning(
                f'[PERMISSION] IsAdminOrHD denied for user {request.user} '
                f'on {view.__class__.__name__}'
            )
        return allowed


class IsEngineer(BasePermission):
    def has_permission(self, request, view):
        allowed = request.user.is_authenticated and request.user.role == 'engineer'
        if not allowed:
            logger.warning(
                f'[PERMISSION] IsEngineer denied for user {request.user} '
                f'on {view.__class__.__name__}'
            )
        return allowed


class IsAdminOrHDOrEngineer(BasePermission):
    def has_permission(self, request, view):
        allowed = request.user.is_authenticated and request.user.role in [
            'admin', 'helpdesk', 'engineer'
        ]
        if not allowed:
            logger.warning(
                f'[PERMISSION] IsAdminOrHDOrEngineer denied for user {request.user} '
                f'on {view.__class__.__name__}'
            )
        return allowed
