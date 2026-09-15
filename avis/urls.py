from django.urls import path

from .views import AvisCreateView, MeilleursAvisView, SignalerAvisView

urlpatterns = [
    path('', AvisCreateView.as_view(), name='avis-create'),
    path('meilleurs/', MeilleursAvisView.as_view(), name='avis-meilleurs'),
    path('<int:pk>/signaler/', SignalerAvisView.as_view(), name='avis-signaler'),
]
