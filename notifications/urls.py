from django.urls import path

from .views import MarquerNotificationLueView, MesNotificationsView, ToutMarquerLuView

urlpatterns = [
    path('', MesNotificationsView.as_view(), name='notifications-liste'),
    path('tout-lire/', ToutMarquerLuView.as_view(), name='notifications-tout-lire'),
    path('<int:pk>/lue/', MarquerNotificationLueView.as_view(), name='notification-lue'),
]
