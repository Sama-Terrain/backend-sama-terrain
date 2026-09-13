from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentification.models import User
from avis.models import Avis
from avis.utils import recalculer_note_terrain
from gerant.models import DemandeGerant
from paiements.models import Abonnement, Paiement
from reservations.models import Reservation
from terrains.models import Terrain

from .permissions import EstAdmin
from .serializers import AdminAvisSerializer, DemandeGerantSerializer

# Durée de l'essai gratuit accordé à un gérant nouvellement validé.
DUREE_ESSAI_JOURS = 7


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
