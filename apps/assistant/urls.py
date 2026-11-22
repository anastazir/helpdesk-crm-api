from django.urls import path

from .views import (
    AnalyticsView,
    AssistantSettingsView,
    ChatView,
    ComplaintAutofillView,
    ComplaintCopilotView,
    DailyBriefingView,
    EngineerPlanView,
    ExportSummaryView,
    GeocodeView,
    TriageView,
)

urlpatterns = [
    path('settings/', AssistantSettingsView.as_view(), name='assistant-settings'),
    path('briefing/', DailyBriefingView.as_view(), name='assistant-briefing'),
    path('analytics/', AnalyticsView.as_view(), name='assistant-analytics'),
    path('geocode/', GeocodeView.as_view(), name='assistant-geocode'),
    path('chat/', ChatView.as_view(), name='assistant-chat'),
    path(
        'complaint-copilot/',
        ComplaintCopilotView.as_view(),
        name='assistant-complaint-copilot',
    ),
    path(
        'complaint-autofill/',
        ComplaintAutofillView.as_view(),
        name='assistant-complaint-autofill',
    ),
    path(
        'engineer-plan/',
        EngineerPlanView.as_view(),
        name='assistant-engineer-plan',
    ),
    path(
        'export-summary/',
        ExportSummaryView.as_view(),
        name='assistant-export-summary',
    ),
    path('triage/', TriageView.as_view(), name='assistant-triage'),
]
