from django.urls import path

from .equipe_views import EmployeDetailView, EmployesView, JournalEquipeView, RenvoyerInvitationView
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
    path('employes/', EmployesView.as_view(), name='gerant-employes'),
    path('employes/<int:pk>/', EmployeDetailView.as_view(), name='gerant-employe-detail'),
    path('employes/<int:pk>/invitation/', RenvoyerInvitationView.as_view(), name='gerant-employe-invitation'),
    path('journal/', JournalEquipeView.as_view(), name='gerant-journal'),
    path('dashboard/', GerantDashboardView.as_view(), name='gerant-dashboard'),
    path('revenus/', GerantRevenusView.as_view(), name='gerant-revenus'),
    path('abonnement/', GerantAbonnementView.as_view(), name='gerant-abonnement'),
    path('portefeuille/', PortefeuilleView.as_view(), name='gerant-portefeuille'),
    path('portefeuille/retraits/', RetraitGerantView.as_view(), name='gerant-retraits'),
    path('insights-ia/', GerantInsightsIAView.as_view(), name='gerant-insights-ia'),
    path('n8n/rapport-hebdomadaire/', RapportHebdomadaireN8nView.as_view(), name='n8n-rapport-hebdomadaire'),
]
