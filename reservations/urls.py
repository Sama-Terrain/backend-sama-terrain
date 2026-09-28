from django.urls import path

from avis.views import AvisPossibleView

from .views import (
    CommandeDetailView,
    MesReservationsView,
    PolitiqueAnnulationView,
    ReservationCreateView,
    ReservationDetailView,
    ReservationGroupeCreateView,
)

urlpatterns = [
    path('', ReservationCreateView.as_view(), name='reservation-create'),
    path('groupe/', ReservationGroupeCreateView.as_view(), name='reservation-groupe-create'),
    path('commande/<int:pk>/', CommandeDetailView.as_view(), name='commande-detail'),
    path('mes-reservations/', MesReservationsView.as_view(), name='mes-reservations'),
    path('<int:pk>/', ReservationDetailView.as_view(), name='reservation-detail'),
    path(
        '<int:pk>/politique-annulation/',
        PolitiqueAnnulationView.as_view(),
        name='reservation-politique-annulation',
    ),
    path('<int:pk>/avis-possible/', AvisPossibleView.as_view(), name='reservation-avis-possible'),
]
