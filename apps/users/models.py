import logging

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

logger = logging.getLogger('apps.users')

ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('helpdesk', 'Help Desk'),
    ('engineer', 'Engineer'),
]


class UserManager(BaseUserManager):
    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email is required.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        logger.info(f'[USER] Created user: {email} | role: {extra_fields.get("role")}')
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_users'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name', 'role']
    objects = UserManager()

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def get_current_zone_ids(self):
        current = {}
        for change in self.zone_assignment_history.order_by('changed_at', 'id'):
            if change.action == 'added':
                current[change.zone_id] = True
            else:
                current.pop(change.zone_id, None)
        return set(current.keys())

    def get_current_zones(self):
        from apps.zones.models import Zone

        return Zone.objects.filter(id__in=self.get_current_zone_ids()).order_by('name')

    def get_active_complaint_count(self):
        if self.role != 'engineer':
            return None
        return self.complaint_assignments.filter(
            unassigned_at__isnull=True
        ).exclude(complaint__status='closed').count()

    def __str__(self):
        return f'{self.full_name} ({self.role})'
