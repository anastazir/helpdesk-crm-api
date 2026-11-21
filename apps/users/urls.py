from django.urls import path

from .views import LoginView, LogoutView, MeView, TokenRefreshAPIView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshAPIView.as_view(), name='token-refresh'),
    path('me/', MeView.as_view(), name='me'),
]
