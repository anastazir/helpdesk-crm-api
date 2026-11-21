from django.urls import path

from .views import ExportDownloadView, ExportPreviewView

urlpatterns = [
    path('preview/', ExportPreviewView.as_view(), name='export-preview'),
    path('download/', ExportDownloadView.as_view(), name='export-download'),
]
