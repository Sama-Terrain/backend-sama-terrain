from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Avg, Count, F, Max, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from creneaux.models import Creneau
from gerant.permissions import EstGerant, EstGerantAbonnementActif, EstN8n
from paiements.models import PRIX_ABONNEMENT_MENSUEL, Abonnement, Paiement, Portefeuille, Retrait
from paiements.portefeuille import RetraitRefuse, demander_retrait, etat_portefeuille
from paiements.serializers import DemandeRetraitSerializer, PortefeuilleSerializer, RetraitSerializer
from reservations.models import Reservation
from reservations.serializers import ReservationSerializer
from terrains.models import Terrain

JOURS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
JOURS_FR_COURT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']


class GerantDashboardView(APIView):
    """
    GET /api/gerant/dashboard/

    Statistiques clés + planning du jour, pour tous les terrains du
    gérant connecté.
    """

    permission_classes = [EstGerantAbonnementActif]

    # get est un endpoint API qui permet de récupérer les statistiques clés et le planning du jour 
    # pour tous les terrains du gérant connecté. Il renvoie le nombre de réservations confirmées pour 
    # aujourd'hui, les revenus du mois, le taux d'occupation des créneaux du mois, la note moyenne des 
    # terrains, et le planning détaillé des réservations confirmées pour aujourd'hui.
    def get(self, request):
        terrains = Terrain.objects.filter(gerant=request.user)
        aujourdhui = timezone.localdate()
        debut_mois = aujourdhui.replace(day=1)

        # On récupère toutes les réservations confirmées pour les terrains du gérant, ainsi que celles qui sont prévues pour aujourd'hui.
        reservations_confirmees = Reservation.objects.filter(
            creneau__terrain__in=terrains, statut=Reservation.Statut.CONFIRMEE
        )

        # On récupère les réservations confirmées pour aujourd'hui, afin de les inclure dans le planning du jour.
        reservations_aujourdhui = reservations_confirmees.filter(creneau__date=aujourdhui)

        # On calcule les revenus du mois en sommant le montant de tous les paiements liés aux 
        # réservations confirmées pour les terrains du gérant, depuis le début du mois.
        revenus_mois = Paiement.objects.filter(
            reservation__creneau__terrain__in=terrains,
            cree_le__date__gte=debut_mois,
        ).exclude(type=Paiement.Type.REMBOURSEMENT).aggregate(total=Sum('montant'))['total'] or 0

        # On calcule le taux d'occupation des créneaux du mois en comparant le nombre de créneaux confirmés
        # avec le nombre total de créneaux pour les terrains du gérant, depuis le début du mois. Si aucun créneau n'est disponible, le taux d'occupation est de 0.
        creneaux_du_mois = Creneau.objects.filter(
            terrain__in=terrains, date__gte=debut_mois, date__lte=aujourdhui
        )
        total_creneaux = creneaux_du_mois.count()
        creneaux_confirmes = creneaux_du_mois.filter(statut=Creneau.Statut.CONFIRME).count()
        taux_occupation = round(creneaux_confirmes / total_creneaux * 100) if total_creneaux else 0

        note_moyenne = terrains.aggregate(moyenne=Avg('note_moyenne'))['moyenne'] or 0

        # On renvoie les statistiques clés et le planning du jour sous forme de dictionnaire JSON,
        return Response({
            'reservations_aujourdhui': reservations_aujourdhui.count(),
            'revenus_mois': revenus_mois,
            'taux_occupation': taux_occupation,
            'note_moyenne': round(note_moyenne, 1),
            'planning_du_jour': ReservationSerializer(
                reservations_aujourdhui.order_by('creneau__heure_debut'), many=True
            ).data,
        })


class GerantRevenusView(APIView):
    """
    GET /api/gerant/revenus/

    Revenus et statistiques de fréquentation, pour tous les terrains du
    gérant connecté.
    """

    permission_classes = [EstGerantAbonnementActif]

    # get est un endpoint API qui permet de récupérer les revenus et les statistiques de fréquentation 
    # pour tous les terrains du gérant connecté. Il renvoie les revenus du mois, les revenus d'hier, 
    # les avances reçues, le solde à percevoir, l'évolution des revenus sur les 30 derniers jours,
    # le nombre de réservations confirmées par jour sur les 7 derniers jours, la répartition des paiements 
    # par moyen de paiement, et l'historique détaillé des paiements 
    def get(self, request):
        terrains = Terrain.objects.filter(gerant=request.user)
        # Un remboursement n'est pas un revenu (avance rendue au joueur).
        paiements = Paiement.objects.filter(reservation__creneau__terrain__in=terrains).exclude(
            type=Paiement.Type.REMBOURSEMENT
        )

        # On calcule les dates importantes pour les statistiques : aujourd'hui, hier, 
        # le début du mois, il y a 30 jours et il y a 7 jours.
        aujourdhui = timezone.localdate()
        hier = aujourdhui - timedelta(days=1)
        debut_mois = aujourdhui.replace(day=1)
        il_y_a_30_jours = aujourdhui - timedelta(days=29)
        il_y_a_7_jours = aujourdhui - timedelta(days=6)

        # On calcule les revenus du mois, les revenus d'hier, les avances reçues et le solde à percevoir pour les terrains du gérant.
        revenus_mois = paiements.filter(cree_le__date__gte=debut_mois).aggregate(
            total=Sum('montant'))['total'] or 0
        revenus_hier = paiements.filter(cree_le__date=hier).aggregate(total=Sum('montant'))['total'] or 0
        avances_recues = paiements.filter(
            type=Paiement.Type.AVANCE, cree_le__date__gte=debut_mois
        ).aggregate(total=Sum('montant'))['total'] or 0

        # On calcule le solde à percevoir en sommant le reste à payer de toutes les réservations confirmées pour les terrains du gérant,
        # en excluant celles qui ont déjà été réglées par un paiement de type "solde".
        reservations_confirmees = Reservation.objects.filter(
            creneau__terrain__in=terrains, statut=Reservation.Statut.CONFIRMEE
        )
        solde_a_percevoir = sum(
            r.reste_a_payer for r in reservations_confirmees
            if not r.paiements.filter(type=Paiement.Type.SOLDE).exists()
        )

        # Revenus jour par jour sur les 30 derniers jours (pour un graphique).
        evolution_30_jours = []
        for i in range(30):
            jour = il_y_a_30_jours + timedelta(days=i)
            montant = paiements.filter(cree_le__date=jour).aggregate(total=Sum('montant'))['total'] or 0
            evolution_30_jours.append({'date': str(jour), 'montant': montant})

        # Nombre de réservations confirmées par jour sur les 7 derniers jours.
        reservations_par_jour = []
        for i in range(7):
            jour = il_y_a_7_jours + timedelta(days=i)
            nombre = reservations_confirmees.filter(creneau__date=jour).count()
            reservations_par_jour.append({'date': str(jour), 'nombre': nombre})

        # Répartition des paiements par moyen de paiement (pour un camembert).
        modes_paiement_stats = list(
            paiements.exclude(moyen_paiement='')
            .values('moyen_paiement')
            .annotate(total=Sum('montant'))
            .order_by('-total')
        )

        # Historique détaillé des paiements (avance + solde), les plus récents
        # d'abord, pour le tableau "Historique des paiements".
        historique_paiements = [
            {
                'id': p.id,
                'date': str(p.cree_le.date()),
                'client': p.reservation.nom_complet,
                'terrain': p.reservation.creneau.terrain.nom,
                'moyen_paiement': p.moyen_paiement,
                'montant': p.montant,
            }
            for p in paiements.select_related(
                'reservation', 'reservation__creneau', 'reservation__creneau__terrain'
            ).order_by('-cree_le')[:50]
        ]

        # On renvoie toutes les statistiques et les données calculées sous forme de dictionnaire JSON.
        return Response({
            'revenus_mois': revenus_mois,
            'revenus_hier': revenus_hier,
            'avances_recues': avances_recues,
            'solde_a_percevoir': solde_a_percevoir,
            'evolution_30_jours': evolution_30_jours,
            'reservations_par_jour': reservations_par_jour,
            'modes_paiement_stats': modes_paiement_stats,
            'historique_paiements': historique_paiements,
        })


class GerantAbonnementView(APIView):
    """
    GET /api/gerant/abonnement/

    Renvoie l'état de l'abonnement du gérant connecté (essai, actif, expiré),
    utilisé pour bloquer l'accès à l'espace gérant si nécessaire et pour
    afficher la page "Abonnement".
    """

    permission_classes = [EstGerant]

    # get est un endpoint API qui permet de récupérer l'état de l'abonnement du gérant connecté (essai, actif, expiré),
    def get(self, request):
        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)

        # On renvoie l'état de l'abonnement sous forme de dictionnaire JSON, avec le statut, 
        # la date de fin d'essai, la date de fin d'abonnement et le prix mensuel.    
        return Response({
            'statut': abonnement.statut,
            'date_fin_essai': abonnement.date_fin_essai,
            'date_fin_abonnement': abonnement.date_fin_abonnement,
            'prix_mensuel': PRIX_ABONNEMENT_MENSUEL,
        })


class PortefeuilleView(APIView):
    """
    GET /api/gerant/portefeuille/ -> solde, numéro de retrait, derniers retraits
    PUT /api/gerant/portefeuille/ -> enregistre le numéro Wave / Orange Money

    Accessible même avec un abonnement expiré : le gérant doit toujours
    pouvoir récupérer l'argent qui lui revient.
    """

    permission_classes = [EstGerant]

    def _reponse(self, gerant):
        portefeuille = Portefeuille.objects.filter(gerant=gerant).first()
        retraits = Retrait.objects.filter(gerant=gerant)[:20]
        return Response({
            **etat_portefeuille(gerant),
            'numero_retrait': PortefeuilleSerializer(portefeuille).data if portefeuille else None,
            'retraits': RetraitSerializer(retraits, many=True).data,
        })

    def get(self, request):
        return self._reponse(request.user)

    def put(self, request):
        portefeuille = Portefeuille.objects.filter(gerant=request.user).first()
        serializer = PortefeuilleSerializer(portefeuille, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(gerant=request.user)
        return self._reponse(request.user)


class RetraitGerantView(APIView):
    """POST /api/gerant/portefeuille/retraits/ -> demande de retrait d'un montant du solde."""

    permission_classes = [EstGerant]

    def post(self, request):
        serializer = DemandeRetraitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            retrait = demander_retrait(request.user, serializer.validated_data['montant'])
        except RetraitRefuse as erreur:
            return Response({'detail': str(erreur)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RetraitSerializer(retrait).data, status=status.HTTP_201_CREATED)


class GerantInsightsIAView(APIView):
    """
    GET /api/gerant/insights-ia/

    Vue d'ensemble IA pour tous les terrains du gérant connecté : rafraîchit
    les prédictions de demande (service IA) pour chaque terrain, puis
    agrège l'occupation réelle des 7 prochains jours, les créneaux dont le
    prix recommandé par l'IA diffère du prix actuel, et des alertes
    dérivées des vraies données (créneaux sous-tarifés, clients fidèles
    inactifs). Comme pour IAPredictionsView, rien n'est inventé : tout part
    de statistiques réelles, éventuellement mises en phrases par le LLM.
    """

    permission_classes = [EstGerantAbonnementActif]

    # get est un endpoint API qui permet de récupérer les insights IA pour tous les terrains du gérant connecté.
    def get(self, request):
        terrains = Terrain.objects.filter(gerant=request.user)

        # On demande au micro-service IA (FastAPI) ses prédictions de demande pour chaque terrain du gérant,
        recommandations_ia = []
        for terrain in terrains:
            try:
                reponse = requests.get(
                    f"{settings.IA_SERVICE_URL}/predictions/{terrain.id}", timeout=5
                )
                reponse.raise_for_status()
                recommandations_ia.extend(reponse.json().get('recommandations', []))
            except requests.RequestException:
                continue

        # On calcule l'occupation réelle des 7 prochains jours pour les terrains du gérant,
        aujourdhui = timezone.localdate()
        occupation_7_jours = []
        for i in range(7):
            jour = aujourdhui + timedelta(days=i)
            creneaux_jour = Creneau.objects.filter(terrain__in=terrains, date=jour)
            total = creneaux_jour.count()
            confirmes = creneaux_jour.filter(statut=Creneau.Statut.CONFIRME).count()
            occupation_7_jours.append({
                'date': str(jour),
                'label': f"{JOURS_FR_COURT[jour.weekday()]} {jour.strftime('%d')}", #weekday() et strftime('%d') permettent de formater la date pour l'affichage dans le tableau de bord.
                'taux': round(confirmes / total * 100) if total else 0,
            })

        # On récupère les créneaux dont le prix recommandé par l'IA diffère du prix actuel, 
        # pour alerter le gérant sur les opportunités de réajustement tarifaire.
        creneaux_repricing = (
            Creneau.objects.filter(
                terrain__in=terrains,
                statut=Creneau.Statut.DISPONIBLE,
                date__gte=aujourdhui,
                prix_recommande_ia__isnull=False,
            )
            .exclude(prix_recommande_ia=F('prix'))
            .select_related('terrain')
            .order_by('date', 'heure_debut')[:3]
        )

        # On prépare la liste des recommandations tarifaires à afficher dans le tableau de bord du gérant,
        recommandations_tarifaires = [
            {
                'id': c.id,
                'terrain': c.terrain.nom,
                'jour': f"{JOURS_FR[c.date.weekday()]} {c.date.strftime('%d/%m')}",
                'creneau': f"{c.heure_debut.strftime('%H:%M')} - {c.heure_fin.strftime('%H:%M')}",
                'prix_actuel': c.prix,
                'prix_recommande': c.prix_recommande_ia,
                'impact_pct': round((c.prix_recommande_ia - c.prix) / c.prix * 100),
            }
            for c in creneaux_repricing
        ]

        alertes = []

        # On vérifie s'il existe un créneau sous-tarifé (prix recommandé par l'IA supérieur au prix 
        # actuel) pour les terrains du gérant, afin de générer une alerte pour le gérant. 
        # On ne prend que le premier créneau trouvé pour éviter de surcharger le tableau de bord.
        creneau_sous_tarife = (
            Creneau.objects.filter(
                terrain__in=terrains,
                statut=Creneau.Statut.DISPONIBLE,
                date__gte=aujourdhui,
                niveau_demande=Creneau.NiveauDemande.ELEVE,
                prix_recommande_ia__isnull=False,
            )
            .exclude(prix_recommande_ia=F('prix')) # F est django.db.models.F, qui permet de comparer deux champs d'un même modèle dans une requête. Ici, on exclut les créneaux dont le prix recommandé par l'IA est égal au prix actuel.
            .select_related('terrain')
            .order_by('date', 'heure_debut')
            .first()
        )
        if creneau_sous_tarife:
            hausse_pct = round(
                (creneau_sous_tarife.prix_recommande_ia - creneau_sous_tarife.prix)
                / creneau_sous_tarife.prix * 100
            )
            alertes.append({
                'type': 'opportunite',
                'titre': f"Créneau {creneau_sous_tarife.heure_debut.strftime('%H:%M')} sous-tarifé",
                'message': (
                    f"La demande pour ce créneau du {creneau_sous_tarife.date.strftime('%d/%m')} "
                    f"est élevée. Augmentation tarifaire suggérée de +{hausse_pct}%."
                ),
                'creneau_id': creneau_sous_tarife.id,
            })

        # On vérifie s'il existe des clients fidèles inactifs (ayant réservé au moins 2 fois mais 
        # n'ayant pas réservé depuis plus de 30 jours) pour les terrains du gérant, afin de générer 
        # une alerte pour le gérant.
        il_y_a_30_jours = aujourdhui - timedelta(days=30)
        clients_fideles_inactifs = (
            Reservation.objects.filter(
                creneau__terrain__in=terrains, statut=Reservation.Statut.CONFIRMEE
            )
            .values('amateur')
            .annotate(nb_reservations=Count('id'), derniere=Max('creneau__date'))
            .filter(nb_reservations__gte=2, derniere__lt=il_y_a_30_jours)
            .count()
        )
        if clients_fideles_inactifs:
            alertes.append({
                'type': 'fidelisation',
                'titre': 'Fidélisation client',
                'message': (
                    f"{clients_fideles_inactifs} client(s) régulier(s) n'ont pas réservé "
                    "depuis plus de 30 jours. Envisagez une offre de relance."
                ),
                'creneau_id': None,
            })

        # On renvoie les recommandations IA, l'occupation réelle des 7 prochains jours,
        # les recommandations tarifaires et les alertes sous forme de dictionnaire JSON.
        return Response({
            'recommandations_ia': recommandations_ia[:4],
            'occupation_7_jours': occupation_7_jours,
            'recommandations_tarifaires': recommandations_tarifaires,
            'alertes': alertes,
        })


def _chiffres_periode(terrains, debut, fin):
    """Chiffres réels d'une période [debut, fin], calculés depuis la base."""
    creneaux = Creneau.objects.filter(terrain__in=terrains, date__range=(debut, fin))
    reservations = Reservation.objects.filter(creneau__in=creneaux)
    confirmees = reservations.filter(
        statut__in=[Reservation.Statut.CONFIRMEE, Reservation.Statut.TERMINEE]
    )

    revenus = Paiement.objects.filter(
        reservation__creneau__terrain__in=terrains, cree_le__date__range=(debut, fin)
    ).exclude(type=Paiement.Type.REMBOURSEMENT).aggregate(total=Sum('montant'))['total'] or 0

    total_creneaux = creneaux.count()
    creneaux_confirmes = creneaux.filter(statut=Creneau.Statut.CONFIRME).count()

    # Heure de début des réservations qui a rapporté le plus sur la période.
    meilleure_heure = (
        confirmees.values('creneau__heure_debut')
        .annotate(revenu=Sum('montant_total'))
        .order_by('-revenu')
        .first()
    )

    return {
        'revenus': revenus,
        'nombre_creneaux': total_creneaux,
        # None quand il n'y a aucun créneau : pas de taux à calculer.
        'taux_remplissage': round(creneaux_confirmes / total_creneaux * 100) if total_creneaux else None,
        'reservations_confirmees': confirmees.count(),
        # Inclut les réservations expirées faute de paiement dans les 15 min.
        'annulations': reservations.filter(statut=Reservation.Statut.ANNULEE).count(),
        'heure_la_plus_rentable': (
            meilleure_heure['creneau__heure_debut'].strftime('%H:%M') if meilleure_heure else None
        ),
    }


class RapportHebdomadaireN8nView(APIView):
    """
    GET /api/gerant/n8n/rapport-hebdomadaire/

    Appelée chaque semaine par N8n (en-tête X-N8N-Token obligatoire).
    Renvoie les vrais chiffres de la semaine écoulée et de la semaine
    d'avant pour chaque gérant actif. L'agent IA de N8n rédige ensuite
    le rapport à partir de ces chiffres et l'envoie au gérant.
    """

    permission_classes = [EstN8n]
    # Pas de JWT ici : l'accès est contrôlé par le jeton N8n uniquement.
    authentication_classes = []

    def get(self, request):
        aujourdhui = timezone.localdate()
        semaine = (aujourdhui - timedelta(days=7), aujourdhui - timedelta(days=1))
        semaine_precedente = (aujourdhui - timedelta(days=14), aujourdhui - timedelta(days=8))

        rapports = []
        for abonnement in Abonnement.objects.select_related('gerant').filter(gerant__is_active=True):
            terrains = Terrain.objects.filter(gerant=abonnement.gerant)
            if not abonnement.est_actif or not terrains.exists():
                continue

            rapports.append({
                'email': abonnement.gerant.email,
                'prenom': abonnement.gerant.prenom,
                'terrains': [t.nom for t in terrains],
                'semaine': _chiffres_periode(terrains, *semaine),
                'semaine_precedente': _chiffres_periode(terrains, *semaine_precedente),
            })

        return Response({
            'debut': str(semaine[0]),
            'fin': str(semaine[1]),
            'rapports': rapports,
        })


class IAPredictionsView(APIView):
    """
    GET /api/ia/predictions/:terrainId/

    Demande au micro-service IA (FastAPI, séparé) ses prédictions de
    demande pour ce terrain. Le service IA n'existe pas encore : cette
    vue est prête, mais renverra un message d'indisponibilité tant qu'il
    ne tourne pas à l'adresse IA_SERVICE_URL.
    """

    permission_classes = [EstGerantAbonnementActif]

    # get est un endpoint API qui permet de récupérer les prédictions de demande pour un terrain donné,
    # en interrogeant le micro-service IA (FastAPI). Si le terrain n'appartient pas au gérant connecté, 
    # on renvoie une erreur 404. Si le service IA est indisponible, on renvoie une erreur 503 avec un message d'indisponibilité.
    def get(self, request, terrain_id):
        terrain = Terrain.objects.filter(pk=terrain_id, gerant=request.user).first()
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            reponse = requests.get(
                f"{settings.IA_SERVICE_URL}/predictions/{terrain_id}",
                timeout=5,
            )
            reponse.raise_for_status()
            return Response(reponse.json())
        except requests.RequestException:
            # Le service IA n'est pas encore démarré/déployé : on répond
            # proprement plutôt que de faire planter le dashboard gérant.
            return Response(
                {'disponible': False, 'message': "Service de prédictions IA indisponible pour le moment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class ChatbotView(APIView):
    """
    POST /api/ia/chatbot/

    Fait suivre le message au micro-service IA (FastAPI), qui répond en
    s'appuyant sur les vrais terrains de la base. Accessible sans connexion
    (le chatbot est sur la page d'accueil publique).
    """

    permission_classes = [AllowAny]

    # post est un endpoint API qui permet d'envoyer un message au micro-service IA (FastAPI) pour 
    # obtenir une réponse du chatbot. Le message est récupéré depuis le corps de la requête. Si 
    # le message est vide, on renvoie une erreur 400. Si le service IA est indisponible ou si une 
    # erreur se produit lors de la requête, on renvoie un message par défaut du chatbot.
    def post(self, request):
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'detail': "Message vide."}, status=status.HTTP_400_BAD_REQUEST)

        # Messages précédents de l'utilisateur (facultatif), utilisés par la
        # réservation assistée. On borne leur nombre et leur taille : ils
        # viennent du navigateur et finissent dans un prompt.
        historique = request.data.get('historique', [])
        if not isinstance(historique, list):
            historique = []
        historique = [str(m)[:500] for m in historique if isinstance(m, str) and m.strip()][-6:]

        try:
            reponse = requests.post(
                f"{settings.IA_SERVICE_URL}/chatbot",
                json={'message': message, 'historique': historique},
                # Doit rester nettement supérieur au timeout LLM côté
                # service IA (45s, voir IA/llm.py) pour laisser une marge
                # de sécurité (réseau, requêtes DB) avant de couper.
                timeout=60,
            )
            reponse.raise_for_status()
            return Response(reponse.json())
        except requests.RequestException:
            return Response({
                'texte': "Je recherche les meilleurs terrains disponibles pour vous. "
                         "Pouvez-vous préciser un quartier de Dakar ou une date ?",
            })

