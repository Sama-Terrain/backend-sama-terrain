from django.urls import path

from .views import TicketDetailView, ValiderTicketView

urlpatterns = [
    path('valider/', ValiderTicketView.as_view(), name='ticket-valider'),
    path('<int:pk>/', TicketDetailView.as_view(), name='ticket-detail'),
]
