from django.urls import path

from .views import (
    AdminActiviteRecenteView,
    AdminAvisListView,
    AdminCroissanceInscriptionsView,
    AdminDashboardView,
    AdminReservationsVilleView,
    AdminStatistiquesView,
    GerantsListView,
    MasquerAvisView,
    RejeterGerantView,
    UtilisateursListView,
    ValiderAvisView,
    ValiderGerantView,
)

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('croissance-inscriptions/', AdminCroissanceInscriptionsView.as_view(), name='admin-croissance-inscriptions'),
    path('reservations-ville/', AdminReservationsVilleView.as_view(), name='admin-reservations-ville'),
    path('activite-recente/', AdminActiviteRecenteView.as_view(), name='admin-activite-recente'),
    path('statistiques/', AdminStatistiquesView.as_view(), name='admin-statistiques'),
    path('utilisateurs/', UtilisateursListView.as_view(), name='admin-utilisateurs-list'),
    path('gerants/', GerantsListView.as_view(), name='admin-gerants-list'),
    path('gerants/<int:pk>/valider/', ValiderGerantView.as_view(), name='admin-gerant-valider'),
    path('gerants/<int:pk>/rejeter/', RejeterGerantView.as_view(), name='admin-gerant-rejeter'),
    path('avis/', AdminAvisListView.as_view(), name='admin-avis-list'),
    path('avis/<int:pk>/masquer/', MasquerAvisView.as_view(), name='admin-avis-masquer'),
    path('avis/<int:pk>/valider/', ValiderAvisView.as_view(), name='admin-avis-valider'),
]
