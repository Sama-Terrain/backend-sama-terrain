from django.urls import path

from .views import (
    MesReservationsView,
    PolitiqueAnnulationView,
    ReservationCreateView,
    ReservationDetailView,
)

urlpatterns = [
    path('', ReservationCreateView.as_view(), name='reservation-create'),
    path('mes-reservations/', MesReservationsView.as_view(), name='mes-reservations'),
    path('<int:pk>/', ReservationDetailView.as_view(), name='reservation-detail'),
    path(
        '<int:pk>/politique-annulation/',
        PolitiqueAnnulationView.as_view(),
        name='reservation-politique-annulation',
    ),
]
