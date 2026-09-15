from django.urls import path

from .views import (
    AbonnementInitierView,
    AbonnementIPNView,
    AlertesExpirationAbonnementView,
    InitierPaiementView,
    PaiementIPNView,
    RappelsReservationsView,
    SoldeView,
)

urlpatterns = [
    path('initier/', InitierPaiementView.as_view(), name='paiement-initier'),
    path('ipn/', PaiementIPNView.as_view(), name='paiement-ipn'),
    path('abonnement/initier/', AbonnementInitierView.as_view(), name='abonnement-initier'),
    path('abonnement/ipn/', AbonnementIPNView.as_view(), name='abonnement-ipn'),
    path('solde/', SoldeView.as_view(), name='paiement-solde'),
    path('n8n/rappels-reservations/', RappelsReservationsView.as_view(), name='n8n-rappels-reservations'),
    path(
        'n8n/alertes-expiration-abonnement/',
        AlertesExpirationAbonnementView.as_view(),
        name='n8n-alertes-expiration-abonnement',
    ),
]
