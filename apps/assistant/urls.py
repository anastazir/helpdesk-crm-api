from django.urls import path

from .views import DailyBriefingView

urlpatterns = [
    path('briefing/', DailyBriefingView.as_view(), name='assistant-briefing'),
]
