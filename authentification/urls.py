from django.urls import path

from .views import RegisterView, VerifyEmailView

urlpatterns = [
    path('register', RegisterView.as_view(), name='auth-register'),
    path('verify-email', VerifyEmailView.as_view(), name='auth-verify-email'),
]
