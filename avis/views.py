from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from reservations.models import Reservation
from terrains.models import Terrain

from .models import Avis
from .serializers import AvisCreateSerializer, AvisSerializer, match_deja_joue
from .utils import recalculer_note_terrain


class TerrainAvisListView(APIView):
    """
    GET /api/terrains/:id/avis/

    Liste publique des avis visibles d'un terrain.
    """

    permission_classes = [AllowAny]

    def get(self, request, terrain_id):
        terrain = Terrain.objects.filter(pk=terrain_id).first()
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        avis = terrain.avis.filter(visible=True).order_by('-cree_le')
        return Response(AvisSerializer(avis, many=True).data)


class AvisPossibleView(APIView):
    """
    GET /api/reservations/:id/avis-possible/

    Indique si l'amateur connecté peut laisser un avis sur cette
    réservation (déjà jouée, confirmée, pas encore notée).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        reservation = Reservation.objects.filter(pk=pk, amateur=request.user).first()
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        deja_note = Avis.objects.filter(reservation=reservation).exists()
        possible = (
            reservation.statut == Reservation.Statut.CONFIRMEE
            and match_deja_joue(reservation)
            and not deja_note
        )

        return Response({'avis_possible': possible, 'deja_note': deja_note})


class AvisCreateView(APIView):
    """
    POST /api/avis/

    Soumet un nouvel avis. Met aussi à jour la note moyenne du terrain.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AvisCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        avis = serializer.save()
        recalculer_note_terrain(avis.terrain)

        return Response(AvisSerializer(avis).data, status=status.HTTP_201_CREATED)


class SignalerAvisView(APIView):
    """
    POST /api/avis/:id/signaler/

    Marque un avis comme signalé, pour qu'un admin puisse ensuite décider
    de le masquer ou de le conserver (voir app admin_panel).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        avis = Avis.objects.filter(pk=pk).first()
        if avis is None:
            return Response({'detail': "Avis introuvable."}, status=status.HTTP_404_NOT_FOUND)

        avis.signale = True
        avis.save()

        return Response({'message': "Avis signalé, il sera examiné par un administrateur."})
