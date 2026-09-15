from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentification.models import User
from creneaux.models import Creneau
from reservations.models import Reservation
from tickets.models import Ticket

from .models import PRIX_ABONNEMENT_MENSUEL, Abonnement, Paiement
from .n8n import notifier_n8n
from .paytech import creer_demande_paiement
from .serializers import InitierPaiementSerializer, SoldeSerializer


class InitierPaiementView(APIView):
    """
    POST /api/paiements/initier/

    Crée une demande de paiement PayTech pour l'avance d'une réservation,
    et renvoie l'URL vers laquelle rediriger l'amateur pour qu'il paie.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InitierPaiementSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation = serializer.validated_data['reservation']
        terrain = reservation.creneau.terrain

        # PayTech refuse un ref_command déjà utilisé (erreur 409). On ajoute
        # un horodatage pour qu'une nouvelle tentative de paiement sur la
        # même réservation (ex: après un paiement annulé) ait un ref_command différent.
        ref_command = f"RES-{reservation.id}-{int(timezone.now().timestamp())}"

        resultat = creer_demande_paiement(
            item_name=f"Réservation {terrain.nom}",
            item_price=reservation.montant_avance,
            ref_command=ref_command,
            ipn_url=f"{settings.BACKEND_URL}/api/paiements/ipn/",
            # On transmet l'id de la réservation dans l'URL de retour : une fois
            # redirigé depuis PayTech, le frontend doit savoir quelle réservation
            # afficher (il ne peut plus compter sur le state React, perdu lors
            # de la sortie du site pour aller payer).
            success_url=f"{settings.FRONTEND_URL}/paiement/succes?reservation={reservation.id}",
            cancel_url=f"{settings.FRONTEND_URL}/paiement/annule?reservation={reservation.id}",
        )

        return Response({'payment_url': resultat['payment_url']}, status=status.HTTP_200_OK)


class PaiementIPNView(APIView):
    """
    POST /api/paiements/ipn/

    Appelée par PayTech (pas par le frontend) une fois le paiement de
    l'avance confirmé. On y met à jour la réservation, on génère le
    ticket QR, et on notifie N8n (email + WhatsApp).
    """

    # PayTech appelle cette route depuis ses propres serveurs, sans JWT.
    permission_classes = [AllowAny]

    def post(self, request):
        # PayTech renvoie le ref_command qu'on avait fourni à la création :
        # il a la forme "RES-<id_reservation>-<timestamp>".
        ref_command = request.data.get('ref_command', '')

        try:
            reservation_id = int(ref_command.split('-')[1])
        except (IndexError, ValueError):
            return Response({'detail': "ref_command invalide."}, status=status.HTTP_400_BAD_REQUEST)

        reservation = Reservation.objects.filter(pk=reservation_id).first()

        if reservation is None:
            return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        reservation.statut = Reservation.Statut.CONFIRMEE
        reservation.moyen_paiement = request.data.get('payment_method', '')
        reservation.transaction_id = request.data.get('token', '')
        reservation.save()

        creneau = reservation.creneau
        creneau.statut = Creneau.Statut.CONFIRME
        creneau.save()

        Paiement.objects.create(
            type=Paiement.Type.AVANCE,
            reservation=reservation,
            montant=reservation.montant_avance,
            moyen_paiement=reservation.moyen_paiement,
            transaction_id=reservation.transaction_id,
        )

        # Un ticket par réservation confirmée. get_or_create évite un doublon
        # si PayTech renvoie la même notification IPN deux fois.
        ticket, _ = Ticket.objects.get_or_create(reservation=reservation)

        notifier_n8n('reservation_confirmee', {
            'email_amateur': reservation.amateur.email,
            'nom_amateur': reservation.amateur.prenom,
            'terrain': creneau.terrain.nom,
            'date': str(creneau.date),
            'heure': str(creneau.heure_debut),
            'code_ticket': str(ticket.code),
        })

        return Response({'message': "Paiement confirmé."}, status=status.HTTP_200_OK)


class AbonnementInitierView(APIView):
    """
    POST /api/paiements/abonnement/initier/

    Crée une demande de paiement PayTech pour l'abonnement mensuel
    (7 500 FCFA) du gérant connecté.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'gerant':
            return Response({'detail': "Réservé aux gérants."}, status=status.HTTP_403_FORBIDDEN)

        # On récupère (ou crée si besoin) l'abonnement de ce gérant.
        Abonnement.objects.get_or_create(gerant=request.user)

        # Le ref_command inclut l'id du gérant : l'IPN en aura besoin pour
        # savoir quel abonnement activer.
        ref_command = f"ABO-{request.user.id}-{int(timezone.now().timestamp())}"

        resultat = creer_demande_paiement(
            item_name="Abonnement mensuel Sama-Terrain",
            item_price=PRIX_ABONNEMENT_MENSUEL,
            ref_command=ref_command,
            ipn_url=f"{settings.BACKEND_URL}/api/paiements/abonnement/ipn/",
            success_url=f"{settings.FRONTEND_URL}/gerant/abonnement/succes",
            cancel_url=f"{settings.FRONTEND_URL}/gerant/abonnement/annule",
        )

        return Response({'payment_url': resultat['payment_url']}, status=status.HTTP_200_OK)


class AbonnementIPNView(APIView):
    """
    POST /api/paiements/abonnement/ipn/

    Appelée par PayTech une fois l'abonnement payé. Active (ou prolonge
    de 30 jours) l'accès du gérant concerné.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        ref_command = request.data.get('ref_command', '')

        # Le ref_command a la forme "ABO-<id_gerant>-<timestamp>".
        try:
            gerant_id = int(ref_command.split('-')[1])
        except (IndexError, ValueError):
            return Response({'detail': "ref_command invalide."}, status=status.HTTP_400_BAD_REQUEST)

        gerant = User.objects.filter(pk=gerant_id).first()
        abonnement = Abonnement.objects.filter(gerant=gerant).first() if gerant else None

        if abonnement is None:
            return Response({'detail': "Abonnement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        maintenant = timezone.now()

        # Si l'abonnement est encore actif, on ajoute 30 jours À PARTIR de
        # sa date de fin actuelle (pour ne pas faire perdre de jours payés).
        # Sinon, on repart de maintenant.
        depart = abonnement.date_fin_abonnement if (
            abonnement.date_fin_abonnement and abonnement.date_fin_abonnement > maintenant
        ) else maintenant

        abonnement.date_fin_abonnement = depart + timedelta(days=30)
        abonnement.statut = Abonnement.Statut.ACTIF
        abonnement.save()

        Paiement.objects.create(
            type=Paiement.Type.ABONNEMENT,
            abonnement=abonnement,
            montant=PRIX_ABONNEMENT_MENSUEL,
            moyen_paiement=request.data.get('payment_method', ''),
            transaction_id=request.data.get('token', ''),
        )

        notifier_n8n('abonnement_active', {
            'email_gerant': abonnement.gerant.email,
            'date_fin_abonnement': str(abonnement.date_fin_abonnement),
        })

        return Response({'message': "Abonnement activé."}, status=status.HTTP_200_OK)


class RappelsReservationsView(APIView):
    """
    GET /api/paiements/n8n/rappels-reservations/

    Appelée périodiquement par N8n (nœud "Schedule Trigger", ex: toutes les
    30 minutes). Cherche les réservations confirmées dont le match a lieu
    dans moins de 3h et pour lesquelles aucun rappel n'a encore été envoyé,
    envoie l'évènement à N8n pour chacune, puis les marque comme "rappel envoyé"
    pour ne jamais les renvoyer deux fois.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        maintenant = timezone.now()
        dans_3h = maintenant + timedelta(hours=3)

        reservations = Reservation.objects.filter(
            statut=Reservation.Statut.CONFIRMEE,
            rappel_envoye=False,
        ).select_related('creneau', 'creneau__terrain', 'amateur')

        nb_envoyes = 0
        for reservation in reservations:
            creneau = reservation.creneau
            debut = timezone.make_aware(
                timezone.datetime.combine(creneau.date, creneau.heure_debut)
            )

            if not (maintenant <= debut <= dans_3h):
                continue

            notifier_n8n('rappel_reservation', {
                'email_amateur': reservation.amateur.email,
                'nom_amateur': reservation.amateur.prenom,
                'terrain': creneau.terrain.nom,
                'date': str(creneau.date),
                'heure': str(creneau.heure_debut),
            })
            reservation.rappel_envoye = True
            reservation.save(update_fields=['rappel_envoye'])
            nb_envoyes += 1

        return Response({'rappels_envoyes': nb_envoyes}, status=status.HTTP_200_OK)


class AlertesExpirationAbonnementView(APIView):
    """
    GET /api/paiements/n8n/alertes-expiration-abonnement/

    Appelée périodiquement par N8n (une fois par jour). Cherche les
    abonnements (essai ou payé) qui expirent dans moins de 3 jours et pour
    lesquels aucune alerte n'a encore été envoyée, notifie N8n pour chacun,
    puis les marque comme "alerte envoyée".
    """

    permission_classes = [AllowAny]

    def get(self, request):
        maintenant = timezone.now()
        dans_3_jours = maintenant + timedelta(days=3)

        abonnements = Abonnement.objects.filter(
            statut__in=[Abonnement.Statut.ESSAI, Abonnement.Statut.ACTIF],
            alerte_expiration_envoyee=False,
        ).select_related('gerant')

        nb_envoyes = 0
        for abonnement in abonnements:
            date_fin = (
                abonnement.date_fin_essai
                if abonnement.statut == Abonnement.Statut.ESSAI
                else abonnement.date_fin_abonnement
            )

            if not date_fin or not (maintenant <= date_fin <= dans_3_jours):
                continue

            notifier_n8n('abonnement_expire_bientot', {
                'email_gerant': abonnement.gerant.email,
                'nom_gerant': abonnement.gerant.prenom,
                'date_fin': str(date_fin),
            })
            abonnement.alerte_expiration_envoyee = True
            abonnement.save(update_fields=['alerte_expiration_envoyee'])
            nb_envoyes += 1

        return Response({'alertes_envoyees': nb_envoyes}, status=status.HTTP_200_OK)


class SoldeView(APIView):
    """
    POST /api/paiements/solde/

    Enregistre manuellement le paiement du solde restant, payé sur place
    en cash ou en mobile money direct (pas via PayTech). C'est le gérant
    qui confirme avoir reçu ce paiement.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SoldeSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation = serializer.validated_data['reservation']

        Paiement.objects.create(
            type=Paiement.Type.SOLDE,
            reservation=reservation,
            montant=reservation.reste_a_payer,
            moyen_paiement=serializer.validated_data['moyen_paiement'],
        )

        return Response({'message': "Paiement du solde enregistré."}, status=status.HTTP_201_CREATED)
