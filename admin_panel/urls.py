from django.urls import path

from .views import (
    AdminAvisListView,
    AdminDashboardView,
    GerantsListView,
    MasquerAvisView,
    RejeterGerantView,
    ValiderAvisView,
    ValiderGerantView,
)

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('gerants/', GerantsListView.as_view(), name='admin-gerants-list'),
    path('gerants/<int:pk>/valider/', ValiderGerantView.as_view(), name='admin-gerant-valider'),
    path('gerants/<int:pk>/rejeter/', RejeterGerantView.as_view(), name='admin-gerant-rejeter'),
    path('avis/', AdminAvisListView.as_view(), name='admin-avis-list'),
    path('avis/<int:pk>/masquer/', MasquerAvisView.as_view(), name='admin-avis-masquer'),
    path('avis/<int:pk>/valider/', ValiderAvisView.as_view(), name='admin-avis-valider'),
]
