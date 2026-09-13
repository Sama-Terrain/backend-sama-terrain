from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from terrains.models import Terrain

from .models import Creneau
from .permissions import EstGerantProprietaireDuTerrain
from .serializers import CreneauCreateSerializer, CreneauSerializer, CreneauUpdateSerializer


class TerrainCreneauxListView(APIView):
    """
    GET /api/terrains/:id/creneaux/

    Liste les créneaux d'un terrain. Route publique (un amateur doit
    pouvoir voir les disponibilités avant de se connecter).
    Filtre optionnel : ?date=2026-03-15
    """

    permission_classes = [AllowAny]

    def get(self, request, terrain_id):
        terrain = Terrain.objects.filter(pk=terrain_id).first()
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        creneaux = terrain.creneaux.all()

        date = request.query_params.get('date')
        if date:
            creneaux = creneaux.filter(date=date)

        return Response(CreneauSerializer(creneaux, many=True).data)


class CreneauCreateView(APIView):
    """
    POST /api/creneaux/

    Crée un créneau pour un des terrains du gérant connecté.
    """

    permission_classes = [EstGerantProprietaireDuTerrain]

    def post(self, request):
        serializer = CreneauCreateSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        creneau = serializer.save()
        return Response(CreneauSerializer(creneau).data, status=status.HTTP_201_CREATED)


class CreneauDetailView(APIView):
    """
    PATCH  /api/creneaux/:id/ -> modifier un créneau (gérant propriétaire)
    DELETE /api/creneaux/:id/ -> supprimer un créneau (gérant propriétaire)
    """

    permission_classes = [EstGerantProprietaireDuTerrain]

    def get_object(self, pk):
        creneau = Creneau.objects.filter(pk=pk).first()
        if creneau is not None:
            self.check_object_permissions(self.request, creneau)
        return creneau

    def patch(self, request, pk):
        creneau = self.get_object(pk)
        if creneau is None:
            return Response({'detail': "Créneau introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CreneauUpdateSerializer(creneau, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        creneau = serializer.save()
        return Response(CreneauSerializer(creneau).data)

    def delete(self, request, pk):
        creneau = self.get_object(pk)
        if creneau is None:
            return Response({'detail': "Créneau introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # On empêche de supprimer un créneau déjà réservé, pour ne pas
        # faire disparaître une réservation existante sans prévenir personne.
        if creneau.statut != Creneau.Statut.DISPONIBLE:
            return Response(
                {'detail': "Impossible de supprimer un créneau réservé ou en attente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creneau.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreneauPrixDynamiqueView(APIView):
    """
    PATCH /api/creneaux/:id/prix-dynamique/

    Applique au créneau le prix recommandé par l'IA (prix_recommande_ia
    devient le nouveau prix affiché aux amateurs).
    """

    permission_classes = [EstGerantProprietaireDuTerrain]

    def patch(self, request, pk):
        creneau = Creneau.objects.filter(pk=pk).first()
        if creneau is None:
            return Response({'detail': "Créneau introuvable."}, status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, creneau)

        if creneau.prix_recommande_ia is None:
            return Response(
                {'detail': "Aucun prix recommandé par l'IA pour ce créneau."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creneau.prix = creneau.prix_recommande_ia
        creneau.save()

        return Response(CreneauSerializer(creneau).data)
