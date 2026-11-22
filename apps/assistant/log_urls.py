from django.urls import path

from .log_views import (
    AIRequestLogDetailView,
    AIRequestLogListView,
    AIRequestLogSummaryView,
)

urlpatterns = [
    path('', AIRequestLogListView.as_view(), name='ai-log-list'),
    path('summary/', AIRequestLogSummaryView.as_view(), name='ai-log-summary'),
    path('<int:log_id>/', AIRequestLogDetailView.as_view(), name='ai-log-detail'),
]
