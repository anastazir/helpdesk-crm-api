import logging

from django.db import models

logger = logging.getLogger('apps.zones')


class Zone(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'zones'
        ordering = ['name']

    def get_current_engineers(self):
        from apps.users.models import User

        latest_actions = {}
        for change in self.engineerzoneassignment_set.order_by('changed_at', 'id'):
            latest_actions[change.engineer_id] = change.action

        engineer_ids = [
            engineer_id
            for engineer_id, action in latest_actions.items()
            if action == 'added'
        ]
        return User.objects.filter(
            id__in=engineer_ids, role='engineer', is_active=True, is_deleted=False
        ).order_by('full_name')

    def get_engineer_count(self):
        return self.get_current_engineers().count()

    def get_complaint_count(self):
        return self.complaints.count()

    def __str__(self):
        return self.name


class EngineerZoneAssignment(models.Model):
    """
    Immutable log of every zone assignment/removal for an engineer.
    Current zones = all 'added' actions minus all 'removed' actions.
    Never delete records from this table.
    """
    ACTION_CHOICES = [('added', 'Added'), ('removed', 'Removed')]

    engineer = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='zone_assignment_history'
    )
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='zone_changes_made'
    )

    class Meta:
        db_table = 'engineer_zone_assignments'
        ordering = ['-changed_at']

    def __str__(self):
        return f'{self.engineer.full_name} {self.action} {self.zone.name}'
