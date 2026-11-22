from django.urls import path

from .views import (
    ChatView,
    ComplaintCopilotView,
    DailyBriefingView,
    EngineerPlanView,
    TriageView,
)

urlpatterns = [
    path('briefing/', DailyBriefingView.as_view(), name='assistant-briefing'),
    path('chat/', ChatView.as_view(), name='assistant-chat'),
    path(
        'complaint-copilot/',
        ComplaintCopilotView.as_view(),
        name='assistant-complaint-copilot',
    ),
    path(
        'engineer-plan/',
        EngineerPlanView.as_view(),
        name='assistant-engineer-plan',
    ),
    path('triage/', TriageView.as_view(), name='assistant-triage'),
]
