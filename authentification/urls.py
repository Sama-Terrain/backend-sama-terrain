from django.urls import path

from .views import (
    GoogleAuthView,
    LoginView,
    RegisterView,
    ResendCodeView,
    VerifyEmailView,
)

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('verify-email', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('resend-code', ResendCodeView.as_view(), name='auth-resend-code'),
    path('login', LoginView.as_view(), name='auth-login'),
    path('google', GoogleAuthView.as_view(), name='auth-google'),
]
