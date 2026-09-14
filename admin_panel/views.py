from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentification.models import User
from avis.models import Avis
from avis.utils import recalculer_note_terrain
from creneaux.models import Creneau
from gerant.models import DemandeGerant
from paiements.models import Abonnement, Paiement
from reservations.models import Reservation
from terrains.models import Terrain

from .permissions import EstAdmin
from .serializers import AdminAvisSerializer, DemandeGerantSerializer

# Durée de l'essai gratuit accordé à un gérant nouvellement validé.
DUREE_ESSAI_JOURS = 7

# Couleurs utilisées pour les graphiques "par ville" (mêmes tons que le reste
# de l'espace admin : vert principal, doré, puis des gris/verts clairs).
COULEURS_VILLES = ['#004030', '#D4AF37', '#A7F3D0', '#CBD5E1', '#94A3B8']


def temps_ecoule(date):
    """Formate une date en texte relatif court, ex: 'Il y a 5 min'."""
    delta = timezone.now() - date
    minutes = int(delta.total_seconds() / 60)

    if minutes < 1:
        return "À l'instant"
    if minutes < 60:
        return f"Il y a {minutes} min"
    heures = minutes // 60
    if heures < 24:
        return f"Il y a {heures} heure{'s' if heures > 1 else ''}"
    jours = heures // 24
    return f"Il y a {jours} jour{'s' if jours > 1 else ''}"


class AdminDashboardView(APIView):
    """
    GET /api/admin/dashboard/

    Statistiques globales de la plateforme.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        revenus_totaux = Paiement.objects.aggregate(total=Sum('montant'))['total'] or 0

        return Response({
            'total_terrains': Terrain.objects.count(),
            'total_utilisateurs': User.objects.count(),
            'total_reservations': Reservation.objects.filter(statut=Reservation.Statut.CONFIRMEE).count(),
            'revenus_totaux': revenus_totaux,
            'gerants_en_attente': DemandeGerant.objects.filter(statut=DemandeGerant.Statut.EN_ATTENTE).count(),
            'avis_signales': Avis.objects.filter(signale=True, visible=True).count(),
        })


class AdminCroissanceInscriptionsView(APIView):
    """
    GET /api/admin/croissance-inscriptions/

    Nombre de nouveaux comptes créés chaque mois de l'année en cours
    (pour le graphique de croissance du tableau de bord).
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        annee = timezone.now().year
        noms_mois = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc']

        data = []
        for mois in range(1, 13):
            nombre = User.objects.filter(date_joined__year=annee, date_joined__month=mois).count()
            data.append({'period': noms_mois[mois - 1], 'value': nombre})

        mois_courant = data[timezone.now().month - 1]['value']
        mois_precedent = data[timezone.now().month - 2]['value'] if timezone.now().month > 1 else 0
        if mois_precedent:
            evolution = round((mois_courant - mois_precedent) / mois_precedent * 100)
            total_mois = f"{'+' if evolution >= 0 else ''}{evolution}% vs mois dernier"
        else:
            total_mois = f"{mois_courant} nouveaux ce mois-ci"

        return Response({'totalMois': total_mois, 'data': data})


class AdminReservationsVilleView(APIView):
    """
    GET /api/admin/reservations-ville/

    Répartition des réservations confirmées par ville (top 5), pour le
    graphique du tableau de bord.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        villes = (
            Reservation.objects.filter(statut=Reservation.Statut.CONFIRMEE)
            .values('creneau__terrain__ville')
            .annotate(total=Count('id'))
            .order_by('-total')[:5]
        )

        return Response([
            {
                'ville': v['creneau__terrain__ville'],
                'rawValue': v['total'],
                'hexColor': COULEURS_VILLES[i % len(COULEURS_VILLES)],
            }
            for i, v in enumerate(villes)
        ])


class AdminActiviteRecenteView(APIView):
    """
    GET /api/admin/activite-recente/

    Flux des derniers événements notables de la plateforme (nouveaux
    terrains, demandes de gérant, avis signalés, nouvelles inscriptions,
    réservations confirmées), toutes catégories mélangées et triées par date.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        evenements = []

        for t in Terrain.objects.order_by('-cree_le')[:5]:
            evenements.append({
                'date': t.cree_le,
                'description': f"Nouveau terrain « {t.nom} » créé par {t.gerant.prenom} {t.gerant.nom}",
                'category': 'Terrain',
                'badgeClass': 'bg-[#e6f4ea] text-[#004030]',
            })

        for d in DemandeGerant.objects.order_by('-cree_le')[:5]:
            evenements.append({
                'date': d.cree_le,
                'description': f"Demande de validation soumise par {d.user.prenom} {d.user.nom} ({d.nom_complexe})",
                'category': 'Gérant',
                'badgeClass': 'bg-amber-100 text-amber-800',
            })

        for a in Avis.objects.filter(signale=True).order_by('-cree_le')[:5]:
            evenements.append({
                'date': a.cree_le,
                'description': f"Avis signalé sur le terrain « {a.terrain.nom} » par {a.amateur.prenom} {a.amateur.nom}",
                'category': 'Modération',
                'badgeClass': 'bg-red-100 text-red-700',
            })

        for u in User.objects.filter(role='amateur').order_by('-date_joined')[:5]:
            evenements.append({
                'date': u.date_joined,
                'description': f"Nouveau joueur inscrit : {u.prenom} {u.nom}",
                'category': 'Inscription',
                'badgeClass': 'bg-sky-100 text-sky-700',
            })

        for p in Paiement.objects.filter(type=Paiement.Type.AVANCE).order_by('-cree_le')[:5]:
            evenements.append({
                'date': p.cree_le,
                'description': f"Réservation confirmée pour RES-{p.reservation_id} - Montant : {p.montant} FCFA",
                'category': 'Paiement',
                'badgeClass': 'bg-amber-50 text-amber-700 border border-amber-200',
            })

        evenements.sort(key=lambda e: e['date'], reverse=True)

        return Response([
            {
                'id': i,
                'time': temps_ecoule(e['date']),
                'description': e['description'],
                'category': e['category'],
                'badgeClass': e['badgeClass'],
            }
            for i, e in enumerate(evenements[:8])
        ])


class AdminStatistiquesView(APIView):
    """
    GET /api/admin/statistiques/

    Statistiques avancées pour la page "Analyses et Statistiques Globales" :
    KPIs de performance, répartition des moyens de paiement, répartition par
    ville, et top 5 des terrains les plus réservés.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        reservations_confirmees = Reservation.objects.filter(statut=Reservation.Statut.CONFIRMEE)

        # --- KPIs ---
        total_creneaux = Creneau.objects.count()
        creneaux_confirmes = Creneau.objects.filter(statut=Creneau.Statut.CONFIRME).count()
        taux_occupation = round(creneaux_confirmes / total_creneaux * 100) if total_creneaux else 0

        terrain_demande = (
            reservations_confirmees.values('creneau__terrain__nom')
            .annotate(total=Count('id'))
            .order_by('-total')
            .first()
        )
        creneau_populaire = (
            reservations_confirmees.values('creneau__heure_debut')
            .annotate(total=Count('id'))
            .order_by('-total')
            .first()
        )
        clients_uniques = reservations_confirmees.values('amateur').distinct().count()

        il_y_a_7_jours = timezone.now() - timedelta(days=7)
        nouveaux_clients = (
            reservations_confirmees.filter(cree_le__gte=il_y_a_7_jours)
            .values('amateur').distinct().count()
        )

        kpis = [
            {
                'title': "Taux d'occupation moyen",
                'value': f"{taux_occupation}%",
                'trend': 'Sur tous les créneaux créés',
            },
            {
                'title': 'Terrain le plus demandé',
                'value': terrain_demande['creneau__terrain__nom'] if terrain_demande else 'Aucun',
                'trend': f"{terrain_demande['total']} réservations" if terrain_demande else '',
            },
            {
                'title': 'Créneau le plus populaire',
                'value': str(creneau_populaire['creneau__heure_debut'])[:5] if creneau_populaire else 'Aucun',
                'trend': f"{creneau_populaire['total']} réservations" if creneau_populaire else '',
            },
            {
                'title': 'Clients uniques',
                'value': str(clients_uniques),
                'trend': f"+{nouveaux_clients} cette semaine",
            },
        ]

        # --- Moyens de paiement (en %) ---
        paiements_par_mode = list(
            Paiement.objects.exclude(moyen_paiement='')
            .values('moyen_paiement')
            .annotate(total=Sum('montant'))
        )
        total_paiements = sum(p['total'] for p in paiements_par_mode) or 1
        montants = {p['moyen_paiement']: p['total'] for p in paiements_par_mode}

        payment_stats = [{
            'name': 'Paiements',
            'Wave': round(montants.get('wave', 0) / total_paiements * 100),
            'OrangeMoney': round(montants.get('orange_money', 0) / total_paiements * 100),
            'Cash': round(montants.get('cash', 0) / total_paiements * 100),
        }]

        # --- Répartition par ville (top 3) ---
        villes = (
            reservations_confirmees.values('creneau__terrain__ville')
            .annotate(total=Count('id'))
            .order_by('-total')[:3]
        )
        total_villes = sum(v['total'] for v in villes) or 1
        city_stats = [
            {
                'name': v['creneau__terrain__ville'],
                'value': round(v['total'] / total_villes * 100),
                'color': COULEURS_VILLES[i % len(COULEURS_VILLES)],
            }
            for i, v in enumerate(villes)
        ]

        # --- Top 5 terrains ---
        top_terrains_qs = (
            reservations_confirmees.values('creneau__terrain__id', 'creneau__terrain__nom', 'creneau__terrain__ville')
            .annotate(total_reservations=Count('id'), total_revenus=Sum('montant_total'))
            .order_by('-total_reservations')[:5]
        )
        top_terrains = [
            {
                'rank': i + 1,
                'terrain': t['creneau__terrain__nom'],
                'ville': t['creneau__terrain__ville'],
                'reservations': f"{t['total_reservations']} matches",
                'chiffre': f"{(t['total_revenus'] or 0):,} FCFA".replace(',', ' '),
            }
            for i, t in enumerate(top_terrains_qs)
        ]

        return Response({
            'kpis': kpis,
            'payment_stats': payment_stats,
            'city_stats': city_stats,
            'top_terrains': top_terrains,
        })


class UtilisateursListView(APIView):
    """
    GET /api/admin/utilisateurs/

    Liste de tous les comptes de la plateforme (amateurs, gérants, admins),
    pour la page "Gestion des utilisateurs".
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        utilisateurs = []

        for user in User.objects.all().order_by('-date_joined'):
            # Le téléphone/quartier ne sont enregistrés que pour les gérants
            # (via leur demande d'inscription) : rien de tel n'existe pour
            # un compte amateur, créé sans ces informations.
            demande = getattr(user, 'demande_gerant', None)

            utilisateurs.append({
                'id': user.id,
                'nom': f"{user.prenom} {user.nom}",
                'email': user.email,
                'telephone': demande.whatsapp if demande else None,
                'ville': demande.quartier if demande else None,
                'role': user.role,
                'date_inscription': user.date_joined,
                'actif': user.is_active,
            })

        return Response(utilisateurs)


class GerantsListView(APIView):
    """
    GET /api/admin/gerants?statut=en_attente

    Liste des demandes de gérant. Filtre optionnel par statut
    (en_attente / validee / rejetee) ; sans filtre, renvoie tout.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        demandes = DemandeGerant.objects.all().order_by('-cree_le')

        statut = request.query_params.get('statut')
        if statut:
            demandes = demandes.filter(statut=statut)

        return Response(DemandeGerantSerializer(demandes, many=True, context={'request': request}).data)


class ValiderGerantView(APIView):
    """
    PATCH /api/admin/gerants/:id/valider/

    Valide la demande : active le compte du gérant et démarre sa
    période d'essai gratuit de 7 jours.
    """

    permission_classes = [EstAdmin]

    def patch(self, request, pk):
        demande = DemandeGerant.objects.filter(pk=pk).first()
        if demande is None:
            return Response({'detail': "Demande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        demande.statut = DemandeGerant.Statut.VALIDEE
        demande.traitee_le = timezone.now()
        demande.save()

        demande.user.is_active = True
        demande.user.save()

        abonnement, _ = Abonnement.objects.get_or_create(gerant=demande.user)
        abonnement.statut = Abonnement.Statut.ESSAI
        abonnement.date_fin_essai = timezone.now() + timedelta(days=DUREE_ESSAI_JOURS)
        abonnement.save()

        return Response({'message': "Gérant validé. Compte activé avec 7 jours d'essai gratuit."})


class RejeterGerantView(APIView):
    """
    PATCH /api/admin/gerants/:id/rejeter/

    Rejette la demande : le compte reste inactif.
    """

    permission_classes = [EstAdmin]

    def patch(self, request, pk):
        demande = DemandeGerant.objects.filter(pk=pk).first()
        if demande is None:
            return Response({'detail': "Demande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        demande.statut = DemandeGerant.Statut.REJETEE
        demande.traitee_le = timezone.now()
        demande.save()

        return Response({'message': "Demande rejetée."})


class AdminAvisListView(APIView):
    """
    GET /api/admin/avis?signale=true

    Liste des avis, filtrable par signalement.
    """

    permission_classes = [EstAdmin]

    def get(self, request):
        avis = Avis.objects.all().order_by('-cree_le')

        if request.query_params.get('signale') == 'true':
            avis = avis.filter(signale=True)

        return Response(AdminAvisSerializer(avis, many=True).data)


class MasquerAvisView(APIView):
    """
    PATCH /api/admin/avis/:id/masquer/

    Masque un avis signalé : il n'apparaît plus publiquement.
    """

    permission_classes = [EstAdmin]

    def patch(self, request, pk):
        avis = Avis.objects.filter(pk=pk).first()
        if avis is None:
            return Response({'detail': "Avis introuvable."}, status=status.HTTP_404_NOT_FOUND)

        avis.visible = False
        avis.save()
        recalculer_note_terrain(avis.terrain)

        return Response({'message': "Avis masqué."})


class ValiderAvisView(APIView):
    """
    PATCH /api/admin/avis/:id/valider/

    Conserve un avis signalé : le signalement est rejeté, l'avis reste visible.
    """

    permission_classes = [EstAdmin]

    def patch(self, request, pk):
        avis = Avis.objects.filter(pk=pk).first()
        if avis is None:
            return Response({'detail': "Avis introuvable."}, status=status.HTTP_404_NOT_FOUND)

        avis.signale = False
        avis.visible = True
        avis.save()
        recalculer_note_terrain(avis.terrain)

        return Response({'message': "Avis conservé."})
