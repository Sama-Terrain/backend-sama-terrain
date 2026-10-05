from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentification.models import User
from creneaux.models import Creneau
from gerant.equipe import journaliser
from gerant.models import JournalAction
from notifications.models import Notification
from notifications.services import notifier, notifier_equipe
from reservations.models import Commande, Reservation
from tickets.models import Ticket

from .models import PRIX_ABONNEMENT_MENSUEL, Abonnement, Paiement
from .n8n import notifier_n8n
from .paytech import creer_demande_paiement, ipn_authentique, paiement_reussi
from .serializers import InitierPaiementGroupeSerializer, InitierPaiementSerializer, SoldeSerializer


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

        # On récupère la réservation et le moyen de paiement choisi par l'amateur.
        reservation = serializer.validated_data['reservation']
        moyen_paiement = serializer.validated_data['moyen_paiement']
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
            # Le moyen déjà choisi dans notre interface : PayTech saute alors
            # sa propre page de choix du moyen de paiement.
            target_payment=moyen_paiement,
        )

        # `reservation.telephone` est stocké au format "221XXXXXXXXX" (voir
        # DetailTerrain.jsx). On l'utilise pour pré-remplir et auto-valider
        # la page PayTech (paramètres documentés par PayTech), afin que
        # l'amateur arrive directement sur l'écran de paiement (QR code Wave,
        # ou saisie OTP Orange Money) sans ressaisir son numéro.
        telephone_national = reservation.telephone.removeprefix('221')

        # On construit l'URL finale vers laquelle rediriger l'amateur, en ajoutant
        # les paramètres de pré-remplissage à l'URL fournie par PayTech.
        #urlencode() transforme un dictionnaire en chaîne de requête (ex: {'a': 1, 'b': 2} devient "a=1&b=2").
        parametres_prefill = urlencode({
            'pn': f"+{reservation.telephone}",
            'nn': telephone_national,
            'fn': f"{reservation.amateur.prenom} {reservation.amateur.nom}",
            'tp': moyen_paiement,
            'nac': '1',
        })

        # On ajoute les paramètres de pré-remplissage à l'URL fournie par PayTech, en utilisant '?' ou '&' selon que l'URL contient déjà des paramètres.
        separateur = '&' if '?' in resultat['payment_url'] else '?'
        payment_url = f"{resultat['payment_url']}{separateur}{parametres_prefill}"

        return Response({'payment_url': payment_url}, status=status.HTTP_200_OK)


class InitierPaiementGroupeView(APIView):
    """
    POST /api/paiements/initier-groupe/

    Comme InitierPaiementView, mais pour une Commande regroupant plusieurs
    réservations (plusieurs créneaux payés en une seule fois) : un seul
    paiement PayTech pour la somme des avances de chaque réservation.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InitierPaiementGroupeSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        commande = serializer.validated_data['commande']
        moyen_paiement = serializer.validated_data['moyen_paiement']
        reservations = list(commande.reservations.filter(statut=Reservation.Statut.EN_ATTENTE))

        avance_totale = sum(r.montant_avance for r in reservations)
        # Toutes les réservations d'une commande partagent le même terrain
        # (imposé à la création, voir ReservationGroupeCreateSerializer).
        terrain = reservations[0].creneau.terrain
        premiere_reservation = reservations[0]

        ref_command = f"GRP-{commande.id}-{int(timezone.now().timestamp())}"

        resultat = creer_demande_paiement(
            item_name=f"Réservation {terrain.nom} ({len(reservations)} créneau(x))",
            item_price=avance_totale,
            ref_command=ref_command,
            ipn_url=f"{settings.BACKEND_URL}/api/paiements/ipn/",
            success_url=f"{settings.FRONTEND_URL}/paiement/succes?commande={commande.id}",
            cancel_url=f"{settings.FRONTEND_URL}/paiement/annule?commande={commande.id}",
            target_payment=moyen_paiement,
        )

        telephone_national = premiere_reservation.telephone.removeprefix('221')
        parametres_prefill = urlencode({
            'pn': f"+{premiere_reservation.telephone}",
            'nn': telephone_national,
            'fn': f"{premiere_reservation.amateur.prenom} {premiere_reservation.amateur.nom}",
            'tp': moyen_paiement,
            'nac': '1',
        })
        separateur = '&' if '?' in resultat['payment_url'] else '?'
        payment_url = f"{resultat['payment_url']}{separateur}{parametres_prefill}"

        return Response({'payment_url': payment_url}, status=status.HTTP_200_OK)


def _confirmer_reservation(reservation, moyen_paiement, transaction_id):
    """
    Marque UNE réservation comme payée : confirme la réservation et son
    créneau, enregistre le Paiement, génère le ticket QR et notifie N8n.
    Partagé entre le paiement d'une réservation seule et celui d'une
    commande groupée (voir PaiementIPNView), pour ne pas dupliquer cette
    logique entre les deux cas.
    """
    reservation.statut = Reservation.Statut.CONFIRMEE
    reservation.moyen_paiement = moyen_paiement
    reservation.transaction_id = transaction_id
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
        'telephone_amateur': reservation.telephone,
        'terrain': creneau.terrain.nom,
        'date': str(creneau.date),
        'heure': str(creneau.heure_debut),
        'code_ticket': str(ticket.code),
    })

    notifier_equipe(
        creneau.terrain.gerant, Notification.Type.RESERVATION, 'Nouvelle réservation',
        f"{reservation.nom_complet} a réservé {creneau.terrain.nom} le {creneau.date.strftime('%d/%m')} "
        f"à {creneau.heure_debut.strftime('%H:%M')} (avance de {reservation.montant_avance} FCFA).",
        f'/gerant/reservations?reservation={reservation.id}',
    )


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
        # "RES-<id_reservation>-<timestamp>" pour une réservation seule, ou
        # "GRP-<id_commande>-<timestamp>" pour plusieurs créneaux payés
        # ensemble (voir InitierPaiementGroupeView).
        if not ipn_authentique(request.data):
            return Response({'detail': "Notification non authentifiée."}, status=status.HTTP_403_FORBIDDEN)

        if not paiement_reussi(request.data):
            return Response({'message': "Paiement annulé : rien à confirmer."}, status=status.HTTP_200_OK)

        ref_command = request.data.get('ref_command', '')
        moyen_paiement = request.data.get('payment_method', '')
        transaction_id = request.data.get('token', '')

        try:
            prefixe, identifiant = ref_command.split('-')[0], int(ref_command.split('-')[1])
        except (IndexError, ValueError):
            return Response({'detail': "ref_command invalide."}, status=status.HTTP_400_BAD_REQUEST)

        if prefixe == 'GRP':
            commande = Commande.objects.filter(pk=identifiant).first()
            if commande is None:
                return Response({'detail': "Commande introuvable."}, status=status.HTTP_404_NOT_FOUND)

            # On ne confirme que les réservations encore en attente : si PayTech
            # renvoie la même notification IPN deux fois, on ne refait pas le
            # travail (déjà fait) pour celles déjà confirmées.
            for reservation in commande.reservations.filter(statut=Reservation.Statut.EN_ATTENTE):
                _confirmer_reservation(reservation, moyen_paiement, transaction_id)
        else:
            reservation = Reservation.objects.filter(pk=identifiant).first()
            if reservation is None:
                return Response({'detail': "Réservation introuvable."}, status=status.HTTP_404_NOT_FOUND)

            _confirmer_reservation(reservation, moyen_paiement, transaction_id)

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

        # On crée la demande de paiement PayTech pour l'abonnement mensuel, avec les URLs de notification et de redirection appropriées.
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
        if not ipn_authentique(request.data):
            return Response({'detail': "Notification non authentifiée."}, status=status.HTTP_403_FORBIDDEN)

        if not paiement_reussi(request.data):
            return Response({'message': "Paiement annulé : rien à activer."}, status=status.HTTP_200_OK)

        ref_command = request.data.get('ref_command', '')

        # Le ref_command a la forme "ABO-<id_gerant>-<timestamp>".
        try:
            gerant_id = int(ref_command.split('-')[1])
        except (IndexError, ValueError):
            return Response({'detail': "ref_command invalide."}, status=status.HTTP_400_BAD_REQUEST)

        # On récupère le gérant et son abonnement correspondant depuis la base de données. 
        # Si l'un ou l'autre n'existe pas, on renvoie une erreur 404.
        gerant = User.objects.filter(pk=gerant_id).first()
        abonnement = Abonnement.objects.filter(gerant=gerant).first() if gerant else None

        if abonnement is None:
            return Response({'detail': "Abonnement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On active ou prolonge l'abonnement de 30 jours à partir de la date de fin actuelle si elle 
        # est encore dans le futur, sinon à partir de maintenant.
        maintenant = timezone.now()

        # Si l'abonnement est encore actif, on ajoute 30 jours À PARTIR de
        # sa date de fin actuelle (pour ne pas faire perdre de jours payés).
        # Sinon, on repart de maintenant.
        depart = abonnement.date_fin_abonnement if (
            abonnement.date_fin_abonnement and abonnement.date_fin_abonnement > maintenant
        ) else maintenant

        # On met à jour la date de fin d'abonnement et le statut, puis on enregistre le paiement dans l'historique.
        abonnement.date_fin_abonnement = depart + timedelta(days=30)
        abonnement.statut = Abonnement.Statut.ACTIF
        abonnement.save()

        # On crée un enregistrement de paiement pour cet abonnement, avec le type "abonnement", 
        # le montant payé, le moyen de paiement et l'identifiant de transaction fournis par PayTech.
        Paiement.objects.create(
            type=Paiement.Type.ABONNEMENT,
            abonnement=abonnement,
            montant=PRIX_ABONNEMENT_MENSUEL,
            moyen_paiement=request.data.get('payment_method', ''),
            transaction_id=request.data.get('token', ''),
        )

        # On notifie N8n pour envoyer un email et un WhatsApp au gérant, 
        # l'informant que son abonnement est activé ou prolongé.
        notifier_n8n('abonnement_active', {
            'email_gerant': abonnement.gerant.email,
            'date_fin_abonnement': str(abonnement.date_fin_abonnement),
        })

        notifier(
            abonnement.gerant, Notification.Type.ABONNEMENT, 'Abonnement activé',
            f"Votre abonnement est actif jusqu'au {timezone.localtime(abonnement.date_fin_abonnement).strftime('%d/%m/%Y')}.",
            '/gerant/abonnement',
        )

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

    # get est un endpoint API qui permet de rechercher les réservations confirmées dont le match a lieu
    # dans moins de 3 heures et pour lesquelles aucun rappel n'a encore été envoyé. Pour chaque réservation trouvée, 
    # il envoie un événement à N8n pour notifier l'amateur, puis marque la réservation comme "rappel envoyé" pour éviter les doublons.
    def get(self, request):
        maintenant = timezone.now()
        dans_3h = maintenant + timedelta(hours=3)

        # On récupère toutes les réservations confirmées dont le rappel n'a pas encore été envoyé, 
        # en utilisant select_related pour optimiser les requêtes et éviter les requêtes supplémentaires 
        # pour accéder aux relations (creneau, terrain, amateur).
        reservations = Reservation.objects.filter(
            statut=Reservation.Statut.CONFIRMEE,
            rappel_envoye=False,
        ).select_related('creneau', 'creneau__terrain', 'amateur')


        # On parcourt les réservations et on vérifie si le début du créneau est dans moins de 3 heures.
        nb_envoyes = 0
        for reservation in reservations:
            creneau = reservation.creneau
            debut = timezone.make_aware(
                timezone.datetime.combine(creneau.date, creneau.heure_debut)
            )

            if not (maintenant <= debut <= dans_3h):
                continue

            # On notifie N8n pour envoyer un email et un WhatsApp à l'amateur, 
            # l'informant que son match approche et qu'il doit se préparer.
            notifier_n8n('rappel_reservation', {
                'email_amateur': reservation.amateur.email,
                'nom_amateur': reservation.amateur.prenom,
                'telephone_amateur': reservation.telephone,
                'terrain': creneau.terrain.nom,
                'date': str(creneau.date),
                'heure': str(creneau.heure_debut),
            })

            # On marque la réservation comme "rappel envoyé" pour ne pas renvoyer le rappel à nouveau.
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


    # get est un endpoint API qui permet de rechercher les abonnements (essai ou payé) qui expirent dans moins de 
    # 3 jours et pour lesquels aucune alerte n'a encore été envoyée.Pour chaque abonnement trouvé, 
    # il notifie N8n pour envoyer un email et un WhatsApp au gérant, puis marque l'abonnement comme 
    # "alerte envoyée" pour éviter les doublons.
    def get(self, request):
        maintenant = timezone.now()
        dans_3_jours = maintenant + timedelta(days=3)

        # On récupère tous les abonnements (essai ou payé) dont l'alerte d'expiration n'a pas encore été envoyée, 
        # en utilisant select_related pour optimiser les requêtes et éviter les requêtes supplémentaires pour accéder aux relations (gérant).
        abonnements = Abonnement.objects.filter(
            statut__in=[Abonnement.Statut.ESSAI, Abonnement.Statut.ACTIF],
            alerte_expiration_envoyee=False,
        ).select_related('gerant')


        # On parcourt les abonnements et on vérifie si la date de fin d'essai ou d'abonnement est dans moins de 3 jours.
        nb_envoyes = 0
        for abonnement in abonnements:
            date_fin = (
                abonnement.date_fin_essai
                if abonnement.statut == Abonnement.Statut.ESSAI
                else abonnement.date_fin_abonnement
            )

            if not date_fin or not (maintenant <= date_fin <= dans_3_jours):
                continue

            # On notifie N8n pour envoyer un email et un WhatsApp au gérant, 
            # l'informant que son abonnement approche de l'expiration et qu'il doit le renouveler.
            notifier_n8n('abonnement_expire_bientot', {
                'email_gerant': abonnement.gerant.email,
                'nom_gerant': abonnement.gerant.prenom,
                'date_fin': str(date_fin),
            })

            notifier(
                abonnement.gerant, Notification.Type.ALERTE, 'Abonnement bientôt expiré',
                f"Votre {'essai gratuit' if abonnement.statut == Abonnement.Statut.ESSAI else 'abonnement'} se termine le "
                f"{timezone.localtime(date_fin).strftime('%d/%m à %H:%M')}. Renouvelez-le pour garder l'accès.",
                '/gerant/abonnement',
            )

            # On marque l'abonnement comme "alerte envoyée" pour ne pas renvoyer l'alerte à nouveau.
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

    # post est un endpoint API qui permet d'enregistrer manuellement le paiement du solde restant 
    # pour une réservation spécifique, payé sur place en cash ou en mobile money direct (pas via PayTech).
    # Il prend l'identifiant de la réservation et le moyen de paiement choisi par l'amateur en paramètre, 
    # et crée un enregistrement de paiement dans la base de données.
    def post(self, request):
        serializer = SoldeSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation = serializer.validated_data['reservation']

        # On vérifie que la réservation appartient bien à l'amateur connecté, qu'elle est 
        # confirmée et qu'elle n'a pas encore été réglée.
        moyen_paiement = serializer.validated_data['moyen_paiement']
        Paiement.objects.create(
            type=Paiement.Type.SOLDE,
            reservation=reservation,
            montant=reservation.reste_a_payer,
            moyen_paiement=moyen_paiement,
            encaisse_par=request.user,
        )

        journaliser(
            request.user, JournalAction.Action.SOLDE_ENCAISSE,
            f"Solde de {reservation.reste_a_payer} FCFA encaissé "
            f"({'espèces' if moyen_paiement == 'cash' else moyen_paiement.replace('_', ' ').title()}) "
            f"pour la réservation de {reservation.nom_complet}",
        )

        return Response({'message': "Paiement du solde enregistré."}, status=status.HTTP_201_CREATED)
