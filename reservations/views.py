from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from creneaux.models import Creneau

from .models import Reservation
from .serializers import ReservationCreateSerializer, ReservationSerializer
from .utils import liberer_les_expirees, liberer_si_expiree


class ReservationCreateView(APIView):
    """
    POST /api/reservations/

    Crée une réservation et bloque immédiatement le créneau (statut
    "en_attente") en attendant le paiement de l'avance via PayTech.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReservationCreateSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation = serializer.save()

        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


class MesReservationsView(APIView):
    """
    GET /api/reservations/mes-reservations/

    Liste des réservations de l'amateur connecté.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        reservations = Reservation.objects.filter(amateur=request.user)
        liberer_les_expirees(reservations)

        return Response(ReservationSerializer(reservations, many=True).data)


class ReservationDetailView(APIView):
    """
    GET    /api/reservations/:id/ -> détail d'une réservation
    DELETE /api/reservations/:id/ -> annuler une réservation

    Accessible par l'amateur qui l'a créée, ou par le gérant du terrain concerné.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        reservation = Reservation.objects.filter(pk=pk).first()
        if reservation is None:
            return None

        est_amateur_proprietaire = reservation.amateur_id == request.user.id
        est_gerant_proprietaire = reservation.creneau.terrain.gerant_id == request.user.id
        if not (est_amateur_proprietaire or est_gerant_proprietaire):
            return 'interdit'

        return liberer_si_expiree(reservation)

    def get(self, request, pk):
        reservation = self.get_object(request, pk)
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if reservation == 'interdit':
            return Response({'detail': "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        return Response(ReservationSerializer(reservation).data)

    def delete(self, request, pk):
        reservation = self.get_object(request, pk)
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if reservation == 'interdit':
            return Response({'detail': "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        if reservation.statut == Reservation.Statut.ANNULEE:
            return Response({'detail': "Cette réservation est déjà annulée."}, status=status.HTTP_400_BAD_REQUEST)

        # Règle métier : remboursement de l'avance si annulation > 24h avant
        # le match, sinon l'avance est conservée par le gérant. Ici on ne
        # fait que calculer et renvoyer l'info : le vrai remboursement
        # d'argent se fera via PayTech dans l'app "paiements".
        remboursement = reservation.remboursement_possible()

        reservation.statut = Reservation.Statut.ANNULEE
        reservation.save()

        creneau = reservation.creneau
        creneau.statut = Creneau.Statut.DISPONIBLE
        creneau.save()

        return Response({
            'message': "Réservation annulée.",
            'remboursement_possible': remboursement,
            'montant_rembourse': reservation.montant_avance if remboursement else 0,
        })


class PolitiqueAnnulationView(APIView):
    """
    GET /api/reservations/:id/politique-annulation/

    Indique, sans rien annuler, si une annulation MAINTENANT donnerait
    droit à un remboursement (utilisé pour afficher un message d'avertissement
    avant que l'amateur ne confirme son annulation).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        reservation = Reservation.objects.filter(pk=pk, amateur=request.user).first()
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        remboursement = reservation.remboursement_possible()

        return Response({
            'remboursement_possible': remboursement,
            'montant_rembourse': reservation.montant_avance if remboursement else 0,
        })


class GerantReservationsView(APIView):
    """
    GET /api/gerant/reservations/

    Liste des réservations reçues sur tous les terrains du gérant connecté.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        reservations = Reservation.objects.filter(creneau__terrain__gerant=request.user)
        liberer_les_expirees(reservations)

        return Response(ReservationSerializer(reservations, many=True).data)
