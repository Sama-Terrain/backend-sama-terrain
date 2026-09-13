from django.urls import path

from .views import CreneauCreateView, CreneauDetailView, CreneauPrixDynamiqueView

urlpatterns = [
    path('', CreneauCreateView.as_view(), name='creneau-create'),
    path('<int:pk>/', CreneauDetailView.as_view(), name='creneau-detail'),
    path('<int:pk>/prix-dynamique/', CreneauPrixDynamiqueView.as_view(), name='creneau-prix-dynamique'),
]
