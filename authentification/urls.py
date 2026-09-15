from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    DevenirGerantView,
    GoogleAuthView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    ResendCodeView,
    VerifyEmailView,
)

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('devenir-gerant', DevenirGerantView.as_view(), name='auth-devenir-gerant'),
    path('verify-email', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('resend-code', ResendCodeView.as_view(), name='auth-resend-code'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('google', GoogleAuthView.as_view(), name='auth-google'),
    path('logout', LogoutView.as_view(), name='auth-logout'),
    path('token/refresh', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('me', MeView.as_view(), name='auth-me'),
]
