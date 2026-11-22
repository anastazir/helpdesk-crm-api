from django.conf import settings
from django.db import models


class AIRequestLog(models.Model):
    FEATURE_CHOICES = [
        ('briefing', 'Daily Briefing'),
        ('chat', 'AI Chat'),
        ('complaint_copilot', 'Complaint Copilot'),
        ('engineer_plan', 'Engineer Day Plan'),
        ('triage', 'AI Triage'),
        ('export_summary', 'Export Summary'),
        ('complaint_autofill', 'Complaint Autofill'),
    ]
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_request_logs',
    )
    feature = models.CharField(max_length=40, choices=FEATURE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    request_text = models.TextField(blank=True, default='')
    response_text = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=255, blank=True, default='')
    provider = models.CharField(max_length=255, blank=True, default='')
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(
        max_digits=14,
        decimal_places=8,
        null=True,
        blank=True,
    )
    cost_inr = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    latency_ms = models.PositiveIntegerField(default=0)
    tools_used = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_request_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['feature', 'status']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.feature} {self.status} at {self.created_at}'
