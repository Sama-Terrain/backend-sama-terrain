from datetime import timedelta

from django.db.models import Count, Q, Sum
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
from paiements.n8n import notifier_n8n
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

    # get est un endpoint API qui permet de récupérer les statistiques globales de la plateforme pour l'espace admin.
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

    # get est un endpoint API qui permet de récupérer le nombre de nouveaux comptes créés 
    # chaque mois de l'année en cours pour l'espace admin. 
    def get(self, request):
        annee = timezone.now().year
        noms_mois = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc']

        data = []

        # On parcourt les mois de l'année en cours et on compte le nombre d'utilisateurs créés pour chaque mois.
        for mois in range(1, 13):
            nombre = User.objects.filter(date_joined__year=annee, date_joined__month=mois).count()
            data.append({'period': noms_mois[mois - 1], 'value': nombre}) #on ajoute le nom du mois et le nombre d'inscriptions à la liste data.

        # On calcule l'évolution par rapport au mois précédent pour afficher un pourcentage d'augmentation ou de diminution.
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

    # get est un endpoint API qui permet de récupérer la répartition des réservations confirmées par ville (top 5) pour l'espace admin.
    def get(self, request):
        villes = (
            Reservation.objects.filter(statut=Reservation.Statut.CONFIRMEE)
            .values('creneau__terrain__ville')
            .annotate(total=Count('id'))
            .order_by('-total')[:5]
        )

        # On renvoie la liste des villes avec le nombre de réservations confirmées et une couleur associée pour le graphique.
        #enumerate() est utilisé pour obtenir l'index de chaque ville dans la liste, afin d'assigner 
        # une couleur différente à chaque ville en utilisant la liste COULEURS_VILLES.
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

    # get est un endpoint API qui permet de récupérer la liste de tous les comptes de la plateforme 
    # (amateurs, gérants, admins) pour l'espace admin.
    def get(self, request):
        utilisateurs = []

        # On parcourt tous les utilisateurs de la base de données, triés par date d'inscription décroissante.
        for user in User.objects.all().order_by('-date_joined'):
            # Le téléphone/quartier ne sont enregistrés que pour les gérants
            # (via leur demande d'inscription) : rien de tel n'existe pour
            # un compte amateur, créé sans ces informations.
            #getattr() est utilisé pour récupérer l'attribut 'demande_gerant' de l'utilisateur,
            # s'il existe, sinon None. Cela permet d'éviter une erreur si l'utilisateur n'a pas 
            # de demande de gérant associée (par exemple, s'il est un amateur ou un admin).
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


class ToggleActifUtilisateurView(APIView):
    """
    PATCH /api/admin/utilisateurs/<int:pk>/toggle-actif/

    Active ou suspend un compte (bascule is_active). Un admin ne peut pas
    se suspendre lui-même, pour ne jamais se retrouver bloqué hors de son
    propre espace.
    """

    permission_classes = [EstAdmin]

    # patch est un endpoint API qui permet d'activer ou de suspendre un compte utilisateur (bascule is_active) pour l'espace admin.
    def patch(self, request, pk):
        utilisateur = User.objects.filter(pk=pk).first()
        if utilisateur is None:
            return Response({'detail': "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On vérifie que l'utilisateur connecté n'essaie pas de suspendre son propre compte,
        # pour éviter de se retrouver bloqué hors de l'espace admin.
        if utilisateur.id == request.user.id:
            return Response(
                {'detail': "Vous ne pouvez pas suspendre votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # On bascule l'état actif du compte utilisateur (is_active) et on enregistre les 
        # modifications dans la base de données.
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save()

        return Response({'id': utilisateur.id, 'actif': utilisateur.is_active})


class SupprimerUtilisateurView(APIView):
    """
    DELETE /api/admin/utilisateurs/<int:pk>/

    Supprime définitivement un compte (et tout ce qui en dépend en cascade :
    terrains, réservations, avis...). Un admin ne peut pas se supprimer
    lui-même, ni supprimer un autre admin (à faire depuis la base si
    vraiment nécessaire, pour éviter un clic malheureux qui viderait
    l'espace admin).
    """

    permission_classes = [EstAdmin]

    # delete est un endpoint API qui permet de supprimer définitivement un compte utilisateur pour l'espace admin.
    def delete(self, request, pk):
        utilisateur = User.objects.filter(pk=pk).first()
        if utilisateur is None:
            return Response({'detail': "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if utilisateur.id == request.user.id:
            return Response(
                {'detail': "Vous ne pouvez pas supprimer votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if utilisateur.role == User.Role.ADMIN:
            return Response(
                {'detail': "Un compte administrateur ne peut pas être supprimé depuis cette page."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        utilisateur.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminGerantDetailView(APIView):
    """
    GET /api/admin/utilisateurs/<int:user_id>/gerant-detail/

    Vue détaillée d'un gérant précis pour l'admin : ses terrains, son
    abonnement, ses revenus et l'historique de ses paiements. Répond aux
    questions "combien gagne ce gérant ?", "où en est son abonnement ?",
    posées à la page "Gestion des utilisateurs" (bouton "Voir").
    """

    permission_classes = [EstAdmin]

    # get est un endpoint API qui permet de récupérer les détails d'un gérant précis pour l'espace admin,
    # y compris ses terrains, son abonnement, ses revenus et l'historique de ses paiements. 
    # Il répond aux questions "combien gagne ce gérant ?", "où en est son abonnement ?", posées à la 
    # page "Gestion des utilisateurs" (bouton "Voir").
    def get(self, request, user_id):
        gerant = User.objects.filter(pk=user_id, role=User.Role.GERANT).first()
        if gerant is None:
            return Response({'detail': "Gérant introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On récupère tous les terrains appartenant au gérant et on prépare les données pour l'affichage dans l'espace admin.
        terrains = Terrain.objects.filter(gerant=gerant)
        terrains_data = [
            {
                'id': t.id,
                'nom': t.nom,
                'ville': t.ville,
                'actif': t.actif,
                'prix_heure': t.prix_heure,
                'note_moyenne': float(t.note_moyenne),
                'nombre_avis': t.nombre_avis,
            }
            for t in terrains
        ]

        # On récupère tous les paiements liés au gérant, soit par ses terrains, soit par son abonnement, et on les trie par date décroissante.
        # Q est utilisé pour combiner les deux conditions de filtrage avec un "OU" logique.
        # Q est une classe de Django qui permet de construire des requêtes complexes avec des conditions "OU" et "ET".
        paiements = Paiement.objects.filter(
            Q(reservation__creneau__terrain__gerant=gerant) | Q(abonnement__gerant=gerant)
        ).order_by('-cree_le')

        # On calcule les revenus totaux et les revenus du mois en cours pour le gérant, en filtrant 
        # les paiements de type "avance" ou "solde" (ceux qui représentent de l'argent reçu par le gérant).
        revenus_terrains = paiements.filter(
            type__in=[Paiement.Type.AVANCE, Paiement.Type.SOLDE]
        )
        revenus_totaux = revenus_terrains.aggregate(total=Sum('montant'))['total'] or 0
        debut_mois = timezone.localdate().replace(day=1)
        revenus_mois = revenus_terrains.filter(
            cree_le__date__gte=debut_mois
        ).aggregate(total=Sum('montant'))['total'] or 0


        # On récupère l'abonnement du gérant (s'il existe) et on prépare les données pour l'affichage dans l'espace admin.
        abonnement = Abonnement.objects.filter(gerant=gerant).first()
        abonnement_data = None
        if abonnement:
            abonnement_data = {
                'statut': abonnement.statut,
                'date_fin_essai': abonnement.date_fin_essai,
                'date_fin_abonnement': abonnement.date_fin_abonnement,
                'est_actif': abonnement.est_actif,
            }

        # On prépare les paiements reçus et les paiements d'abonnement pour l'affichage dans 
        # l'espace admin, en sérialisant chaque paiement avec ses informations pertinentes.
        def serialiser_paiement(p):
            return {
                'id': p.id,
                'type': p.type,
                'montant': p.montant,
                'moyen_paiement': p.moyen_paiement,
                'cree_le': p.cree_le,
            }

        # Séparés explicitement : l'un est de l'argent que le gérant REÇOIT
        # (ses clients), l'autre de l'argent qu'il PAIE (son abonnement
        # mensuel à la plateforme) — les mélanger prêterait à confusion.
        paiements_recus = [
            serialiser_paiement(p) for p in paiements
            if p.type in (Paiement.Type.AVANCE, Paiement.Type.SOLDE)
        ][:20]
        paiements_abonnement = [
            serialiser_paiement(p) for p in paiements
            if p.type == Paiement.Type.ABONNEMENT
        ][:20]


        # On renvoie toutes les données préparées pour l'affichage dans l'espace admin,
        # y compris les informations du gérant, ses terrains, ses revenus, son abonnement et l'historique de ses paiements.
        return Response({
            'gerant': {
                'id': gerant.id,
                'nom': f"{gerant.prenom} {gerant.nom}",
                'email': gerant.email,
            },
            'terrains': terrains_data,
            'nombre_terrains': len(terrains_data),
            'revenus_totaux': revenus_totaux,
            'revenus_mois': revenus_mois,
            'abonnement': abonnement_data,
            'paiements_recus': paiements_recus,
            'paiements_abonnement': paiements_abonnement,
        })


class GerantsListView(APIView):
    """
    GET /api/admin/gerants?statut=en_attente

    Liste des demandes de gérant. Filtre optionnel par statut
    (en_attente / validee / rejetee) ; sans filtre, renvoie tout.
    """

    permission_classes = [EstAdmin]

    # get est un endpoint API qui permet de récupérer la liste des demandes de gérant pour l'espace admin,
    # avec un filtre optionnel par statut (en_attente / validee / rejetee). Sans filtre, il renvoie toutes les demandes.
    def get(self, request):
        demandes = DemandeGerant.objects.all().order_by('-cree_le')

        statut = request.query_params.get('statut')

        # Si un statut est fourni dans les paramètres de requête, on filtre les demandes de gérant en fonction de ce statut.
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

        # On valide la demande de gérant en mettant à jour son statut et la date de traitement, 
        # puis on active le compte utilisateur associé.
        demande.statut = DemandeGerant.Statut.VALIDEE
        demande.traitee_le = timezone.now()
        demande.save()

        demande.user.is_active = True
        demande.user.save()

        # On crée ou récupère l'abonnement du gérant et on le configure pour une période d'essai gratuit de 7 jours.
        abonnement, _ = Abonnement.objects.get_or_create(gerant=demande.user)
        abonnement.statut = Abonnement.Statut.ESSAI
        abonnement.date_fin_essai = timezone.now() + timedelta(days=DUREE_ESSAI_JOURS)
        abonnement.save()

        notifier_n8n('demande_gerant_validee', {
            'email_gerant': demande.user.email,
            'nom_gerant': demande.user.prenom,
            # Stocké avec un "+" (voir DevenirGerant.jsx) : l'API WhatsApp
            # Business veut le numéro international SANS le "+".
            'telephone_gerant': demande.whatsapp.lstrip('+'),
            'date_fin_essai': str(abonnement.date_fin_essai.date()),
        })

        return Response({'message': "Gérant validé. Compte activé avec 7 jours d'essai gratuit."})


class RejeterGerantView(APIView):
    """
    PATCH /api/admin/gerants/:id/rejeter/

    Rejette la demande : un motif est obligatoire (envoyé par email à la
    personne), puis le compte (jamais activé) est supprimé pour libérer
    l'email et lui permettre de soumettre une nouvelle demande.
    """

    permission_classes = [EstAdmin]

    def patch(self, request, pk):
        demande = DemandeGerant.objects.filter(pk=pk).first()
        if demande is None:
            return Response({'detail': "Demande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On récupère le motif de rejet depuis les données de la requête et on vérifie qu'il est fourni.
        # Le motif est obligatoire pour informer la personne du rejet de sa demande.
        # On utilise .strip() pour enlever les espaces avant et après le motif, afin d'éviter un motif vide.
        motif = request.data.get('motif', '').strip()
        if not motif:
            return Response(
                {'motif': ["Le motif du rejet est obligatoire."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # On rejette la demande de gérant en mettant à jour son statut et la date de traitement, 
        # puis on envoie une notification par email à la personne concernée.
        user = demande.user
        notifier_n8n('demande_gerant_rejetee', {
            'email_gerant': user.email,
            'nom_gerant': user.prenom,
            'motif': motif,
        })

        # Le compte n'a jamais été activé : on le supprime entièrement (la
        # demande est supprimée avec, via CASCADE) pour que la personne
        # puisse resoumettre une demande avec le même email.
        user.delete()

        return Response({'message': "Demande rejetée. La personne a été notifiée par email."})


class AdminAvisListView(APIView):
    """
    GET /api/admin/avis?signale=true

    Liste des avis, filtrable par signalement.
    """

    permission_classes = [EstAdmin]

    # get est un endpoint API qui permet de récupérer la liste des avis pour l'espace admin, 
    # avec un filtre optionnel par signalement (signale=true).
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

    # patch est un endpoint API qui permet de masquer un avis signalé pour l'espace admin,
    # afin qu'il n'apparaisse plus publiquement. Il met à jour l'attribut "visible" de l'avis à 
    # False et recalcul la note moyenne du terrain associé.
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

    # patch est un endpoint API qui permet de conserver un avis signalé pour l'espace admin,
    # en rejetant le signalement et en laissant l'avis visible. Il met à jour l'attribut "signale" 
    # de l'avis à False et recalcul la note moyenne du terrain associé.
    def patch(self, request, pk):
        avis = Avis.objects.filter(pk=pk).first()
        if avis is None:
            return Response({'detail': "Avis introuvable."}, status=status.HTTP_404_NOT_FOUND)

        avis.signale = False
        avis.visible = True
        avis.save()
        recalculer_note_terrain(avis.terrain)

        return Response({'message': "Avis conservé."})
