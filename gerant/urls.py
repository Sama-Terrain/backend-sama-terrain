from django.urls import path

from .views import GerantAbonnementView, GerantDashboardView, GerantInsightsIAView, GerantRevenusView

urlpatterns = [
    path('dashboard/', GerantDashboardView.as_view(), name='gerant-dashboard'),
    path('revenus/', GerantRevenusView.as_view(), name='gerant-revenus'),
    path('abonnement/', GerantAbonnementView.as_view(), name='gerant-abonnement'),
    path('insights-ia/', GerantInsightsIAView.as_view(), name='gerant-insights-ia'),
]
