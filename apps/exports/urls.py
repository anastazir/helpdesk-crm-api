from django.urls import path

from .views import (
    ExportDownloadView,
    ExportPreviewView,
    UserAuditExportDownloadView,
    UserAuditExportPreviewView,
)

urlpatterns = [
    path('preview/', ExportPreviewView.as_view(), name='export-preview'),
    path('download/', ExportDownloadView.as_view(), name='export-download'),
    path('user-audit/preview/', UserAuditExportPreviewView.as_view(), name='user-audit-export-preview'),
    path('user-audit/download/', UserAuditExportDownloadView.as_view(), name='user-audit-export-download'),
]
