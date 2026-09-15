from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from creneaux.models import Creneau

from .models import Terrain, TerrainPhoto
from .permissions import EstGerantOuLectureSeule, EstProprietaireDuTerrain
from .serializers import (
    TerrainCreateUpdateSerializer,
    TerrainDetailSerializer,
    TerrainListSerializer,
)


class TerrainListCreateView(APIView):
    """
    GET  /api/terrains/  -> liste publique des terrains actifs (avec filtres)
    POST /api/terrains/  -> créer un terrain (gérant uniquement)
    """

    permission_classes = [EstGerantOuLectureSeule]

    # Nécessaire pour recevoir des fichiers (photos) en plus des champs texte.
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        # ?mine=true : un gérant connecté demande SES terrains (page "Mes
        # terrains"), y compris ceux qu'il a désactivés. Sinon, c'est le
        # catalogue public, qui ne montre que les terrains actifs.
        mine = request.query_params.get('mine') == 'true'

        if mine:
            if not request.user.is_authenticated or request.user.role != 'gerant':
                return Response({'detail': "Réservé aux gérants."}, status=status.HTTP_403_FORBIDDEN)
            terrains = Terrain.objects.filter(gerant=request.user)
        else:
            terrains = Terrain.objects.filter(actif=True)

            # Filtre par ville, ex: /api/terrains/?ville=Dakar
            ville = request.query_params.get('ville')
            if ville:
                terrains = terrains.filter(ville__iexact=ville)

            # Filtre par date/heure : ne garder que les terrains ayant un
            # créneau DISPONIBLE à ce moment précis.
            # Ex: /api/terrains/?date=2026-03-15&heure=18:00
            date = request.query_params.get('date')
            heure = request.query_params.get('heure')
            if date:
                filtres_creneau = {'creneaux__date': date, 'creneaux__statut': Creneau.Statut.DISPONIBLE}
                if heure:
                    filtres_creneau['creneaux__heure_debut'] = heure
                terrains = terrains.filter(**filtres_creneau).distinct()

        serializer = TerrainListSerializer(
            terrains, many=True, context={'request': request, 'stats_gerant': mine}
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = TerrainCreateUpdateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        terrain = serializer.save(gerant=request.user)
        self._enregistrer_photos(terrain, request)

        return Response(
            TerrainDetailSerializer(terrain, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    def _enregistrer_photos(self, terrain, request):
        """Crée une TerrainPhoto pour chaque fichier envoyé sous la clé 'photos'."""
        photos = request.FILES.getlist('photos')
        for photo in photos:
            TerrainPhoto.objects.create(terrain=terrain, image=photo)


class TerrainDetailView(APIView):
    """
    GET    /api/terrains/:id/  -> détail d'un terrain
    PATCH  /api/terrains/:id/  -> modifier (gérant propriétaire uniquement)
    DELETE /api/terrains/:id/  -> supprimer (gérant propriétaire uniquement)
    """

    permission_classes = [EstGerantOuLectureSeule, EstProprietaireDuTerrain]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk):
        terrain = Terrain.objects.filter(pk=pk).first()
        if terrain is not None:
            # Vérifie les droits (ex: propriétaire) pour ce terrain précis.
            self.check_object_permissions(self.request, terrain)
        return terrain

    def get(self, request, pk):
        terrain = self.get_object(pk)
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TerrainDetailSerializer(terrain, context={'request': request, 'stats_gerant': True})
        return Response(serializer.data)

    def patch(self, request, pk):
        terrain = self.get_object(pk)
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TerrainCreateUpdateSerializer(terrain, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        terrain = serializer.save()

        # "actif" est géré à la main plutôt que via le serializer : avec des
        # données multipart/form-data, un BooleanField DRF absent du formulaire
        # est traité comme False (convention HTML des cases à cocher), ce qui
        # écraserait le statut actif à chaque modification sans rapport.
        if 'actif' in request.data:
            terrain.actif = str(request.data.get('actif')).lower() == 'true'
            terrain.save()

        # Si de nouvelles photos sont envoyées, on les ajoute à celles existantes.
        for photo in request.FILES.getlist('photos'):
            TerrainPhoto.objects.create(terrain=terrain, image=photo)

        return Response(TerrainDetailSerializer(terrain, context={'request': request, 'stats_gerant': True}).data)

    def delete(self, request, pk):
        terrain = self.get_object(pk)
        if terrain is None:
            return Response({'detail': "Terrain introuvable."}, status=status.HTTP_404_NOT_FOUND)

        terrain.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
