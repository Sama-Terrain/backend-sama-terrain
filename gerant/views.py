from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Avg, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from creneaux.models import Creneau
from gerant.permissions import EstGerant, EstGerantAbonnementActif
from paiements.models import PRIX_ABONNEMENT_MENSUEL, Abonnement, Paiement
from reservations.models import Reservation
from reservations.serializers import ReservationSerializer
from terrains.models import Terrain


class GerantDashboardView(APIView):
    """
    GET /api/gerant/dashboard/

    Statistiques clés + planning du jour, pour tous les terrains du
    gérant connecté.
    """

    permission_classes = [EstGerantAbonnementActif]

    def get(self, request):
        terrains = Terrain.objects.filter(gerant=request.user)
        aujourdhui = timezone.localdate()
        debut_mois = aujourdhui.replace(day=1)

        reservations_confirmees = Reservation.objects.filter(
            creneau__terrain__in=terrains, statut=Reservation.Statut.CONFIRMEE
        )

        reservations_aujourdhui = reservations_confirmees.filter(creneau__date=aujourdhui)

        revenus_mois = Paiement.objects.filter(
            reservation__creneau__terrain__in=terrains,
            cree_le__date__gte=debut_mois,
        ).aggregate(total=Sum('montant'))['total'] or 0

        creneaux_du_mois = Creneau.objects.filter(
            terrain__in=terrains, date__gte=debut_mois, date__lte=aujourdhui
        )
        total_creneaux = creneaux_du_mois.count()
        creneaux_confirmes = creneaux_du_mois.filter(statut=Creneau.Statut.CONFIRME).count()
        taux_occupation = round(creneaux_confirmes / total_creneaux * 100) if total_creneaux else 0

        note_moyenne = terrains.aggregate(moyenne=Avg('note_moyenne'))['moyenne'] or 0

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

    def get(self, request):
        terrains = Terrain.objects.filter(gerant=request.user)
        paiements = Paiement.objects.filter(reservation__creneau__terrain__in=terrains)

        aujourdhui = timezone.localdate()
        hier = aujourdhui - timedelta(days=1)
        debut_mois = aujourdhui.replace(day=1)
        il_y_a_30_jours = aujourdhui - timedelta(days=29)
        il_y_a_7_jours = aujourdhui - timedelta(days=6)

        revenus_mois = paiements.filter(cree_le__date__gte=debut_mois).aggregate(
            total=Sum('montant'))['total'] or 0
        revenus_hier = paiements.filter(cree_le__date=hier).aggregate(total=Sum('montant'))['total'] or 0
        avances_recues = paiements.filter(
            type=Paiement.Type.AVANCE, cree_le__date__gte=debut_mois
        ).aggregate(total=Sum('montant'))['total'] or 0

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

    def get(self, request):
        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)

        return Response({
            'statut': abonnement.statut,
            'date_fin_essai': abonnement.date_fin_essai,
            'date_fin_abonnement': abonnement.date_fin_abonnement,
            'prix_mensuel': PRIX_ABONNEMENT_MENSUEL,
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

    def post(self, request):
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'detail': "Message vide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            reponse = requests.post(
                f"{settings.IA_SERVICE_URL}/chatbot",
                json={'message': message},
                timeout=15,
            )
            reponse.raise_for_status()
            return Response(reponse.json())
        except requests.RequestException:
            return Response({
                'texte': "Je recherche les meilleurs terrains disponibles pour vous. "
                         "Pouvez-vous préciser un quartier de Dakar ou une date ?",
            })
