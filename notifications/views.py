from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer
from .services import supprimer_anciennes_lues

# Nombre de notifications renvoyées à la cloche (les plus récentes).
NOTIFICATIONS_AFFICHEES = 30


class MesNotificationsView(APIView):
    """
    GET /api/notifications/

    Les notifications de l'utilisateur connecté (gérant ou admin), les plus
    récentes d'abord, avec le nombre total de non lues.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Nettoyage au fil de l'eau : pas besoin de tâche planifiée pour
        # que les vieilles notifications lues finissent par disparaître.
        supprimer_anciennes_lues(destinataire=request.user)

        notifications = Notification.objects.filter(destinataire=request.user)
        return Response({
            'non_lues': notifications.filter(lue=False).count(),
            'notifications': NotificationSerializer(notifications[:NOTIFICATIONS_AFFICHEES], many=True).data,
        })


class MarquerNotificationLueView(APIView):
    """POST /api/notifications/:id/lue/ — marque UNE notification comme lue."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        mise_a_jour = Notification.objects.filter(pk=pk, destinataire=request.user).update(lue=True)
        if not mise_a_jour:
            return Response({'detail': "Notification introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response({'message': "Notification marquée comme lue."})


class ToutMarquerLuView(APIView):
    """POST /api/notifications/tout-lire/ — marque toutes les notifications comme lues."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        nombre = Notification.objects.filter(destinataire=request.user, lue=False).update(lue=True)
        return Response({'marquees': nombre})
