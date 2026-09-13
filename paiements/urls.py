from django.urls import path

from .views import (
    AbonnementInitierView,
    AbonnementIPNView,
    InitierPaiementView,
    PaiementIPNView,
    SoldeView,
)

urlpatterns = [
    path('initier/', InitierPaiementView.as_view(), name='paiement-initier'),
    path('ipn/', PaiementIPNView.as_view(), name='paiement-ipn'),
    path('abonnement/initier/', AbonnementInitierView.as_view(), name='abonnement-initier'),
    path('abonnement/ipn/', AbonnementIPNView.as_view(), name='abonnement-ipn'),
    path('solde/', SoldeView.as_view(), name='paiement-solde'),
]
