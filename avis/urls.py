from django.urls import path

from .views import AvisCreateView, SignalerAvisView

urlpatterns = [
    path('', AvisCreateView.as_view(), name='avis-create'),
    path('<int:pk>/signaler/', SignalerAvisView.as_view(), name='avis-signaler'),
]
