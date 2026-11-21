from rest_framework.routers import SimpleRouter

from .views import ZoneViewSet

router = SimpleRouter()
router.register('', ZoneViewSet, basename='zone')

urlpatterns = router.urls
