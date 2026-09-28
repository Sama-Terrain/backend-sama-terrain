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

    # get est un endpoint API qui permet de récupérer les détails d'un ticket spécifique, identifié par son identifiant (pk).
    # Il vérifie que l'utilisateur connecté est soit l'amateur propriétaire de la réservation associée au ticket, 
    # soit le gérant du terrain concerné par le ticket. Si l'utilisateur est autorisé, il renvoie les détails du ticket sous forme de JSON.
    def get(self, request, pk):
        ticket = Ticket.objects.filter(pk=pk).first()
        if ticket is None:
            return Response({'detail': "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On vérifie que l'utilisateur connecté est soit l'amateur propriétaire de la réservation 
        # associée au ticket, soit le gérant du terrain concerné par le ticket.
        est_amateur = ticket.reservation.amateur_id == request.user.id
        est_gerant = ticket.reservation.creneau.terrain.gerant_id == request.user.id

        # Si l'utilisateur n'est ni l'amateur ni le gérant, on renvoie une réponse 403 (Accès refusé).
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

    # post est un endpoint API qui permet de valider un ticket en marquant son statut comme "utilisé".
    # Il prend le code du ticket en paramètre, vérifie que le ticket existe,
    # qu'il appartient à un de nos terrains, qu'il n'a pas déjà été utilisé, que la réservation n'a pas été annulée et que la date du match correspond à aujourd'hui
    # Si toutes les conditions sont remplies, le ticket est marqué comme utilisé et la date d'utilisation est enregistrée.
    # La réponse renvoie un message de succès et les détails du ticket validé.
    def post(self, request):
        if request.user.role != 'gerant':
            return Response({'detail': "Réservé aux gérants."}, status=status.HTTP_403_FORBIDDEN)

        # On utilise le serializer ValiderTicketSerializer pour valider le code du ticket fourni dans la requête.
        serializer = ValiderTicketSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # On récupère le ticket validé par le serializer et on le marque comme utilisé, en enregistrant la date et l'heure de l'utilisation.
        ticket = serializer.ticket
        ticket.utilise = True
        ticket.utilise_le = timezone.now()
        ticket.save()

        return Response({
            'message': "Ticket validé.",
            'ticket': TicketSerializer(ticket).data,
        })
