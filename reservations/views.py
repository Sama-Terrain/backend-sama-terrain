from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from creneaux.models import Creneau
from notifications.models import Notification
from notifications.services import notifier
from paiements.models import Paiement

from .models import Commande, Reservation
from .serializers import ReservationCreateSerializer, ReservationGroupeCreateSerializer, ReservationSerializer
from .utils import liberer_les_expirees, liberer_si_expiree


class ReservationCreateView(APIView):
    """
    POST /api/reservations/

    Crée une réservation et bloque immédiatement le créneau (statut
    "en_attente") en attendant le paiement de l'avance via PayTech.
    """

    permission_classes = [IsAuthenticated]

    # On ne peut pas utiliser un ModelViewSet ici, car on ne veut pas que l'amateur puisse créer une réservation pour quelqu'un d'autre (il faut que ce soit lui-même).
    # On ne peut pas non plus utiliser un CreateAPIView, car on veut renvoyer un objet Reservation complet (avec le ticket, le terrain, etc.) plutôt qu'un simple ID.
    def post(self, request):
        serializer = ReservationCreateSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation = serializer.save()

        return Response(ReservationSerializer(reservation, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ReservationGroupeCreateView(APIView):
    """
    POST /api/reservations/groupe/

    Crée plusieurs réservations d'un coup (un même terrain, plusieurs
    créneaux) regroupées dans une Commande, pour un paiement PayTech
    unique de l'avance totale (voir InitierPaiementGroupeView).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReservationGroupeCreateSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        commande, reservations = serializer.save()

        return Response(
            {
                'commande': commande.id,
                'reservations': ReservationSerializer(reservations, many=True, context={'request': request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CommandeDetailView(APIView):
    """
    GET /api/reservations/commande/:id/

    Détail d'une commande (ses réservations), utilisé par la page de
    paiement pour afficher le récapitulatif et par la page de succès pour
    vérifier que TOUTES les réservations du groupe ont bien été confirmées.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        commande = Commande.objects.filter(pk=pk, amateur=request.user).first()
        if commande is None:
            return Response({'detail': "Commande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        reservations = liberer_les_expirees(commande.reservations.all())

        return Response({
            'commande': commande.id,
            'reservations': ReservationSerializer(reservations, many=True, context={'request': request}).data,
        })


class MesReservationsView(APIView):
    """
    GET /api/reservations/mes-reservations/

    Liste des réservations de l'amateur connecté.
    """

    permission_classes = [IsAuthenticated]

    # On applique liberer_si_expiree() à toute la liste des réservations de l'amateur connecté, 
    # pour annuler celles qui ont expiré et libérer les créneaux correspondants.
    # Cela permet de ne pas laisser des créneaux bloqués indéfiniment si l'amateur ne finalise pas son paiement.
    def get(self, request):
        reservations = Reservation.objects.filter(amateur=request.user)
        liberer_les_expirees(reservations)

        return Response(ReservationSerializer(reservations, many=True, context={'request': request}).data)


class ReservationDetailView(APIView):
    """
    GET    /api/reservations/:id/ -> détail d'une réservation
    DELETE /api/reservations/:id/ -> annuler une réservation

    Accessible par l'amateur qui l'a créée, ou par le gérant du terrain concerné.
    """

    permission_classes = [IsAuthenticated]

    # get_object est une méthode interne à la classe, pas un endpoint API. Elle est utilisée 
    # pour récupérer une réservation spécifique par son identifiant (pk) et vérifier les permissions 
    # de l'utilisateur connecté pour cette réservation.   
    def get_object(self, request, pk):
        reservation = Reservation.objects.filter(pk=pk).first()
        if reservation is None:
            return None

        est_amateur_proprietaire = reservation.amateur_id == request.user.id
        est_gerant_proprietaire = reservation.creneau.terrain.gerant_id == request.user.id
        if not (est_amateur_proprietaire or est_gerant_proprietaire):
            return 'interdit'

        return liberer_si_expiree(reservation)


    # get est un endpoint API qui permet de récupérer les détails d'une réservation spécifique. Il utilise
    # la méthode get_object pour récupérer la réservation par son identifiant (pk) et vérifier les permissions
    # de l'utilisateur connecté. Si la réservation est trouvée et que l'utilisateur a les droits d'accès, 
    # elle renvoie les données de la réservation. Sinon, elle renvoie une réponse d'erreur appropriée (404 si la réservation n'existe pas, 403 si l'accès est refusé).
    def get(self, request, pk):
        reservation = self.get_object(request, pk)
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if reservation == 'interdit':
            return Response({'detail': "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        return Response(ReservationSerializer(reservation, context={'request': request}).data)


    # delete est un endpoint API qui permet d'annuler une réservation spécifique. Il utilise
    # la méthode get_object pour récupérer la réservation par son identifiant (pk) et vérifier les permissions
    # de l'utilisateur connecté. Si la réservation est trouvée et que l'utilisateur a les droits d'accès, elle annule la réservation et libère le créneau correspondant.
    def delete(self, request, pk):
        reservation = self.get_object(request, pk)
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if reservation == 'interdit':
            return Response({'detail': "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        if reservation.statut == Reservation.Statut.ANNULEE:
            return Response({'detail': "Cette réservation est déjà annulée."}, status=status.HTTP_400_BAD_REQUEST)

        # Règle métier : remboursement de l'avance (moins les frais de
        # transaction, à la charge du joueur) si annulation > 24h avant
        # le match, sinon l'avance est conservée par le gérant. Ici on ne
        # fait que calculer et renvoyer l'info : le vrai remboursement
        # d'argent se fera via PayTech dans l'app "paiements".
        remboursement = reservation.remboursement_possible()

        # Avance déjà payée et remboursable : on le note dans l'historique,
        # pour qu'elle ne soit pas comptée dans le solde du gérant (voir
        # paiements/portefeuille.py). Le remboursement est fait par l'admin.
        if remboursement and reservation.statut == Reservation.Statut.CONFIRMEE:
            Paiement.objects.create(
                type=Paiement.Type.REMBOURSEMENT,
                reservation=reservation,
                montant=reservation.montant_remboursable(),
                moyen_paiement=reservation.moyen_paiement,
            )

        reservation.statut = Reservation.Statut.ANNULEE
        reservation.annule_le = timezone.now()
        reservation.save()

        creneau = reservation.creneau
        creneau.statut = Creneau.Statut.DISPONIBLE
        creneau.save()

        notifier(
            creneau.terrain.gerant, Notification.Type.ANNULATION, 'Réservation annulée',
            f"{reservation.nom_complet} a annulé son créneau du {creneau.date.strftime('%d/%m')} "
            f"à {creneau.heure_debut.strftime('%H:%M')} sur {creneau.terrain.nom}.",
            f'/gerant/reservations?reservation={reservation.id}',
        )

        # On renvoie le montant remboursé (0 si pas de remboursement) pour que le frontend puisse l'afficher à l'utilisateur.
        return Response({
            'message': "Réservation annulée.",
            'remboursement_possible': remboursement,
            'montant_rembourse': reservation.montant_remboursable(),
            'frais_annulation': reservation.frais_annulation() if remboursement else 0,
        })


class PolitiqueAnnulationView(APIView):
    """
    GET /api/reservations/:id/politique-annulation/

    Indique, sans rien annuler, si une annulation MAINTENANT donnerait
    droit à un remboursement (utilisé pour afficher un message d'avertissement
    avant que l'amateur ne confirme son annulation).
    """

    permission_classes = [IsAuthenticated]

    # get est un endpoint API qui permet de vérifier si une annulation d'une réservation spécifique donnerait droit à un remboursement. Il utilise
    # la méthode get_object pour récupérer la réservation par son identifiant (pk) et vérifier les permissions de l'utilisateur connecté. 
    # Si la réservation est trouvée et que l'utilisateur a les droits d'accès, elle renvoie les informations sur la possibilité de remboursement. Sinon, elle renvoie une  réponse d'erreur appropriée (404 si la réservation n'existe pas, 403 si l'accès est refusé).
    def get(self, request, pk):
        reservation = Reservation.objects.filter(pk=pk, amateur=request.user).first()
        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        remboursement = reservation.remboursement_possible()

        return Response({
            'remboursement_possible': remboursement,
            'montant_rembourse': reservation.montant_remboursable(),
            'frais_annulation': reservation.frais_annulation() if remboursement else 0,
        })


class GerantReservationsView(APIView):
    """
    GET /api/gerant/reservations/

    Liste des réservations reçues sur tous les terrains du gérant connecté.
    """

    permission_classes = [IsAuthenticated]

    # On ne peut pas utiliser un ModelViewSet ici, car on ne veut pas que le gérant puisse voir les réservations d'un autre gérant.
    # On ne peut pas non plus utiliser un ListAPIView, car on veut renvoyer un objet Reservation complet (avec le ticket, le terrain, etc.) plutôt qu'un simple ID.
    def get(self, request):
        reservations = Reservation.objects.filter(creneau__terrain__gerant=request.user)
        liberer_les_expirees(reservations)

        return Response(ReservationSerializer(reservations, many=True, context={'request': request}).data)
