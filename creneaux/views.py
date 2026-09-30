from django.utils import timezone
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

        # Filtre par date si demandé, ex: /api/terrains/42/creneaux/?date=2026-03-15
        date = request.query_params.get('date')

        #on filtre les créneaux par date si le paramètre "date" est présent dans la requête. 
        # Cela permet aux utilisateurs de voir uniquement les créneaux disponibles pour une date spécifique.
        if date:
            creneaux = creneaux.filter(date=date)

        # Un créneau du jour dont l'heure de début est déjà passée ne peut
        # plus être réservé : inutile de le montrer comme "disponible".
        maintenant = timezone.localtime() #localtime() renvoie la date et l'heure actuelles dans le fuseau horaire local du serveur. Cela permet de comparer correctement les créneaux avec l'heure actuelle.

        # on exclut les créneaux du jour dont l'heure de début est déjà passée. Cela permet d'éviter de montrer des créneaux qui ne peuvent plus être réservés.
        #lt signifie "less than" (inférieur à) et est utilisé pour filtrer les créneaux dont l'heure de début est antérieure à l'heure actuelle.
        creneaux = creneaux.exclude(date=maintenant.date(), heure_debut__lt=maintenant.time())

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

    # get_object est une méthode interne à la classe, pas un endpoint API. Elle est utilisée pour 
    # récupérer un créneau spécifique par son identifiant (pk) et vérifier les permissions de l'utilisateur connecté pour ce créneau.
    def get_object(self, pk):
        creneau = Creneau.objects.filter(pk=pk).first()

        # Si le créneau existe, on vérifie les droits (ex: propriétaire du terrain) pour ce créneau précis.
        if creneau is not None:
            self.check_object_permissions(self.request, creneau)
        return creneau

    # patch est un endpoint API qui permet de modifier un créneau existant. Il utilise
    # la méthode get_object pour récupérer le créneau par son identifiant (pk) et vérifier les permissions
    # de l'utilisateur connecté. Si le créneau est trouvé et que les données envoyées sont valides, 
    # il met à jour le créneau et renvoie les données mises à jour.
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

        # Supprimer le terrain complet d'un terrain divisible supprime aussi
        # ses portions (même heure) : elles ne doivent donc pas être réservées.
        portions = creneau.creneaux_en_conflit() if creneau.portion == 0 else Creneau.objects.none()
        if portions.exclude(statut=Creneau.Statut.DISPONIBLE).exists():
            return Response(
                {'detail': "Impossible de supprimer ce créneau : une de ses portions est déjà réservée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        portions.delete()
        creneau.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreneauPrixDynamiqueView(APIView):
    """
    PATCH /api/creneaux/:id/prix-dynamique/

    Applique au créneau le prix recommandé par l'IA (prix_recommande_ia
    devient le nouveau prix affiché aux amateurs).
    """

    permission_classes = [EstGerantProprietaireDuTerrain]


    # patch est un endpoint API qui permet de mettre à jour le prix d'un créneau avec le prix recommandé par l'IA.
    # Il utilise la méthode get_object pour récupérer le créneau par son identifiant (pk) et vérifier les permissions de l'utilisateur connecté. 
    # Si le créneau est trouvé et que le prix recommandé par l'IA est disponible, il met à jour le prix du créneau et renvoie les données mises à jour.
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
