import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger('apps.complaints')

STATUS_CHOICES = [
    ('open', 'Open'),
    ('assigned', 'Assigned'),
    ('in_progress', 'In Progress'),
    ('parts_requested', 'Parts Requested'),
    ('parts_provided', 'Parts Provided'),
    ('resolved', 'Resolved'),
    ('closed', 'Closed'),
]

VALID_STATUS_TRANSITIONS = {
    'open': ['assigned'],
    'assigned': ['in_progress'],
    'in_progress': ['parts_requested', 'resolved'],
    'parts_requested': ['parts_provided'],
    'parts_provided': ['resolved'],
    'resolved': ['closed'],
    'closed': ['resolved'],
}

FILE_TYPE_CHOICES = [('image', 'Image'), ('pdf', 'PDF')]


class IssueType(models.Model):
    """
    Predefined list of hardware issues. Seeded from the PDF form.
    Admin-manageable in the future, for now read-only from the API.
    """
    name = models.CharField(max_length=255, unique=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'issue_types'
        ordering = ['order']

    def __str__(self):
        return self.name


class Complaint(models.Model):
    """
    Core entity. id is a 6-digit integer starting from 100001.
    """
    id = models.PositiveIntegerField(primary_key=True, editable=False)
    caller_phone = models.CharField(max_length=20)
    caller_name = models.CharField(max_length=255, null=True, blank=True)
    bmid = models.CharField(max_length=100, null=True, blank=True)
    aadhaar = models.CharField(max_length=20, null=True, blank=True)
    zone = models.ForeignKey(
        'zones.Zone', on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints'
    )
    department = models.CharField(max_length=255, null=True, blank=True)
    designation = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    address_remark = models.TextField(null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geocode_status = models.CharField(
        max_length=20,
        choices=[
            ('not_geocoded', 'Not geocoded'),
            ('address', 'Address match'),
            ('landmark', 'Landmark approximate'),
            ('pincode', 'Pincode area'),
            ('manual', 'Manually pinned'),
            ('not_found', 'Not found'),
            ('failed', 'Failed'),
        ],
        default='not_geocoded',
    )
    geocode_label = models.CharField(max_length=500, blank=True, default='')
    geocode_provider = models.CharField(max_length=50, blank=True, default='')
    geocode_updated_at = models.DateTimeField(null=True, blank=True)
    map_radius_m = models.PositiveIntegerField(null=True, blank=True)
    cpu_serial = models.CharField(max_length=100, null=True, blank=True)
    monitor_serial = models.CharField(max_length=100, null=True, blank=True)
    issues = models.ManyToManyField(IssueType, blank=True, related_name='complaints')
    others_description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='complaints_created'
    )

    class Meta:
        db_table = 'complaints'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.id:
            last = Complaint.objects.order_by('-id').first()
            self.id = (last.id + 1) if last else 100001
            logger.info(f'[COMPLAINT] New complaint ID assigned: {self.id}')
        super().save(*args, **kwargs)

    def get_current_assignment(self):
        """Returns the active ComplaintAssignment or None."""
        return self.assignments.filter(unassigned_at__isnull=True).select_related('engineer').first()

    def get_assigned_engineer(self):
        """Returns the currently assigned User (engineer) or None."""
        assignment = self.get_current_assignment()
        return assignment.engineer if assignment else None

    def get_time_open_seconds(self):
        """
        Seconds since complaint was created.
        If closed, counts until the closed timestamp instead of now.
        """
        closed_entry = self.status_history.filter(new_status='closed').order_by('-changed_at').first()
        end_time = closed_entry.changed_at if closed_entry else timezone.now()
        return (end_time - self.created_at).total_seconds()

    def get_time_in_status_seconds(self):
        """Seconds since the complaint entered its current status."""
        latest = self.status_history.order_by('-changed_at').first()
        if not latest:
            return (timezone.now() - self.created_at).total_seconds()
        return (timezone.now() - latest.changed_at).total_seconds()

    def __str__(self):
        return f'Complaint #{self.id} — {self.status}'


class ComplaintAssignment(models.Model):
    """
    Immutable log of every engineer assignment on a complaint.
    Active assignment: unassigned_at is NULL.
    Only one record should have unassigned_at=NULL per complaint at any time.
    Never delete records.
    """
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='assignments')
    engineer = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='complaint_assignments'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='assignments_made'
    )
    unassigned_at = models.DateTimeField(null=True, blank=True)
    unassigned_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='unassignments_made'
    )

    class Meta:
        db_table = 'complaint_assignments'
        ordering = ['-assigned_at']

    def __str__(self):
        status = 'active' if not self.unassigned_at else 'past'
        return f'#{self.complaint_id} → {self.engineer.full_name} ({status})'


class StatusHistory(models.Model):
    """
    Immutable log of every status change on a complaint.
    Never update or delete records.
    """
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='status_history')
    previous_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='status_changes'
    )
    remark = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'status_history'
        ordering = ['-changed_at']

    def __str__(self):
        return f'#{self.complaint_id}: {self.previous_status} → {self.new_status}'


class JobNote(models.Model):
    """
    One-per-complaint free-text note from the engineer requesting parts.
    Creating a JobNote automatically sets complaint status to 'parts_requested'.
    """
    complaint = models.OneToOneField(Complaint, on_delete=models.CASCADE, related_name='job_note')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='job_notes'
    )

    class Meta:
        db_table = 'job_notes'

    def __str__(self):
        return f'Job note for #{self.complaint_id}'


class Comment(models.Model):
    """
    Internal comments on a complaint. Never deleted.
    Can only be edited by the author if they are the last commenter.
    """
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='comments')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_edited = models.BooleanField(default=False)

    class Meta:
        db_table = 'comments'
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author.full_name} on #{self.complaint_id}'


class FileUpload(models.Model):
    """
    File evidence uploaded by the engineer (photos or PDF of signed form).
    Never deleted. upload_batch groups files from the same upload event.
    """
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='uploads')
    file = models.FileField(upload_to='complaint_uploads/%Y/%m/%d/')
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    original_name = models.CharField(max_length=255)
    upload_batch = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, related_name='uploads'
    )

    class Meta:
        db_table = 'file_uploads'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Upload batch {self.upload_batch} for #{self.complaint_id}'
