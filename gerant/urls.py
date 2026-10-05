from django.urls import path

from .views import (
    GerantAbonnementView,
    GerantDashboardView,
    GerantInsightsIAView,
    GerantRevenusView,
    PortefeuilleView,
    RetraitGerantView,
    RapportHebdomadaireN8nView,
)

urlpatterns = [
    path('dashboard/', GerantDashboardView.as_view(), name='gerant-dashboard'),
    path('revenus/', GerantRevenusView.as_view(), name='gerant-revenus'),
    path('abonnement/', GerantAbonnementView.as_view(), name='gerant-abonnement'),
    path('portefeuille/', PortefeuilleView.as_view(), name='gerant-portefeuille'),
    path('portefeuille/retraits/', RetraitGerantView.as_view(), name='gerant-retraits'),
    path('insights-ia/', GerantInsightsIAView.as_view(), name='gerant-insights-ia'),
    path('n8n/rapport-hebdomadaire/', RapportHebdomadaireN8nView.as_view(), name='n8n-rapport-hebdomadaire'),
]
