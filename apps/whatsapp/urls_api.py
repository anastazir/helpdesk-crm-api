from django.urls import path

from .api_views import WhatsAppMeView, WhatsAppSettingsView

urlpatterns = [
    path('settings/', WhatsAppSettingsView.as_view(), name='whatsapp-settings'),
    path('me/', WhatsAppMeView.as_view(), name='whatsapp-me'),
]
