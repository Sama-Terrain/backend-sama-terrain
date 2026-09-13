from django.urls import path

from avis.views import TerrainAvisListView
from creneaux.views import TerrainCreneauxListView

from .views import TerrainDetailView, TerrainListCreateView

urlpatterns = [
    path('', TerrainListCreateView.as_view(), name='terrain-list-create'),
    path('<int:pk>/', TerrainDetailView.as_view(), name='terrain-detail'),
    path('<int:terrain_id>/creneaux/', TerrainCreneauxListView.as_view(), name='terrain-creneaux'),
    path('<int:terrain_id>/avis/', TerrainAvisListView.as_view(), name='terrain-avis'),
]
