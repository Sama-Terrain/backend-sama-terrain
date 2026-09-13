from django.urls import path

from .views import GerantDashboardView, GerantRevenusView

urlpatterns = [
    path('dashboard/', GerantDashboardView.as_view(), name='gerant-dashboard'),
    path('revenus/', GerantRevenusView.as_view(), name='gerant-revenus'),
]
