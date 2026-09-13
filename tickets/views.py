from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Ticket
from .serializers import TicketSerializer, ValiderTicketSerializer


class TicketDetailView(APIView):
    """
    GET /api/tickets/:id/

    Accessible par l'amateur propriétaire de la réservation, ou par le
    gérant du terrain concerné.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        ticket = Ticket.objects.filter(pk=pk).first()
        if ticket is None:
            return Response({'detail': "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        est_amateur = ticket.reservation.amateur_id == request.user.id
        est_gerant = ticket.reservation.creneau.terrain.gerant_id == request.user.id
        if not (est_amateur or est_gerant):
            return Response({'detail': "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        return Response(TicketSerializer(ticket).data)


class ValiderTicketView(APIView):
    """
    POST /api/tickets/valider/

    Le gérant scanne (ou saisit) le code du ticket à l'entrée du terrain.
    Si tout est bon, le ticket est marqué comme utilisé (un ticket ne
    peut servir qu'une seule fois).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'gerant':
            return Response({'detail': "Réservé aux gérants."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ValiderTicketSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ticket = serializer.ticket
        ticket.utilise = True
        ticket.utilise_le = timezone.now()
        ticket.save()

        return Response({
            'message': "Ticket validé.",
            'ticket': TicketSerializer(ticket).data,
        })
