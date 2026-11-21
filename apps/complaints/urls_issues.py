from django.urls import path

from .views import IssueTypeListView

urlpatterns = [
    path('', IssueTypeListView.as_view(), name='issue-list'),
]
