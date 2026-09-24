from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangerMotDePasseView,
    DevenirGerantView,
    GoogleAuthView,
    LoginView,
    LogoutView,
    MeView,
    MotDePasseOublieView,
    ReinitialiserMotDePasseView,
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
    path('mot-de-passe', ChangerMotDePasseView.as_view(), name='auth-changer-mot-de-passe'),
    path('mot-de-passe-oublie', MotDePasseOublieView.as_view(), name='auth-mot-de-passe-oublie'),
    path('reinitialiser-mot-de-passe', ReinitialiserMotDePasseView.as_view(), name='auth-reinitialiser-mot-de-passe'),
]
