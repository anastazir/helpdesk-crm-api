from django.contrib import admin

from .models import (
    Comment,
    Complaint,
    ComplaintAssignment,
    FileUpload,
    IssueType,
    JobNote,
    StatusHistory,
)


@admin.register(IssueType)
class IssueTypeAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['id', 'caller_name', 'caller_phone', 'zone', 'status', 'created_at']
    list_filter = ['status', 'zone']
    search_fields = ['id', 'caller_name', 'caller_phone']


@admin.register(ComplaintAssignment)
class ComplaintAssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'complaint', 'engineer', 'assigned_at', 'unassigned_at']


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'complaint', 'previous_status', 'new_status', 'changed_at', 'changed_by']


@admin.register(JobNote)
class JobNoteAdmin(admin.ModelAdmin):
    list_display = ['id', 'complaint', 'created_at', 'created_by']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'complaint', 'author', 'created_at', 'is_edited']


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ['id', 'complaint', 'file_type', 'original_name', 'upload_batch', 'uploaded_at']
