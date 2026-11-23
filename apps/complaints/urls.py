from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ComplaintKPIView, ComplaintViewSet, ZonePerformanceView

router = SimpleRouter()
router.register('', ComplaintViewSet, basename='complaint')

urlpatterns = [
    path('kpis/', ComplaintKPIView.as_view(), name='complaint-kpis'),
    path(
        'zone-performance/',
        ZonePerformanceView.as_view(),
        name='complaint-zone-performance',
    ),
] + router.urls
