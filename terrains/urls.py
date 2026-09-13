from django.urls import path

from .views import TerrainDetailView, TerrainListCreateView

urlpatterns = [
    path('', TerrainListCreateView.as_view(), name='terrain-list-create'),
    path('<int:pk>/', TerrainDetailView.as_view(), name='terrain-detail'),
]
