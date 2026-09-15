from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from paiements.models import Paiement
from reservations.models import Reservation

from .models import Terrain, TerrainPhoto


class TerrainPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerrainPhoto
        fields = ['id', 'image']


class TerrainListSerializer(serializers.ModelSerializer):
    """
    Utilisé pour GET /api/terrains/ (liste publique).
    On ne renvoie pas tous les détails ici, juste ce qu'il faut pour
    afficher une carte de terrain dans le catalogue.
    """

    # La première photo du terrain, utilisée comme image de la carte.
    image = serializers.SerializerMethodField()

    # Ces deux champs ne sont calculés que pour le gérant (voir "mine=true"
    # dans TerrainListCreateView) : inutile de faire ces requêtes en plus
    # pour le catalogue public, qui ne les affiche pas.
    reservations_mois = serializers.SerializerMethodField()
    revenus_mois = serializers.SerializerMethodField()
    taux_occupation = serializers.SerializerMethodField()

    class Meta:
        model = Terrain
        fields = [
            'id', 'nom', 'ville', 'adresse', 'type', 'surface',
            'prix_heure', 'avance', 'note_moyenne', 'nombre_avis',
            'actif', 'equipements', 'description', 'image',
            'heure_ouverture', 'heure_fermeture',
            'reservations_mois', 'revenus_mois', 'taux_occupation',
        ]

    def get_image(self, terrain):
        premiere_photo = terrain.photos.first()
        if not premiere_photo:
            return None
        request = self.context.get('request')
        url = premiere_photo.image.url
        # build_absolute_uri transforme "/media/xxx.jpg" en une URL complète
        # (http://.../media/xxx.jpg) utilisable directement par le frontend.
        return request.build_absolute_uri(url) if request else url

    def get_reservations_mois(self, terrain):
        if not self.context.get('stats_gerant'):
            return None
        debut_mois = timezone.localdate().replace(day=1)
        return Reservation.objects.filter(
            creneau__terrain=terrain,
            statut=Reservation.Statut.CONFIRMEE,
            creneau__date__gte=debut_mois,
        ).count()

    def get_revenus_mois(self, terrain):
        if not self.context.get('stats_gerant'):
            return None
        debut_mois = timezone.localdate().replace(day=1)
        total = Paiement.objects.filter(
            reservation__creneau__terrain=terrain,
            cree_le__date__gte=debut_mois,
        ).aggregate(total=Sum('montant'))['total']
        return total or 0

    def get_taux_occupation(self, terrain):
        if not self.context.get('stats_gerant'):
            return None
        debut_mois = timezone.localdate().replace(day=1)
        creneaux_du_mois = terrain.creneaux.filter(date__gte=debut_mois)
        total = creneaux_du_mois.count()
        if not total:
            return 0
        confirmes = creneaux_du_mois.filter(statut='confirme').count()
        return round(confirmes / total * 100)


class TerrainDetailSerializer(TerrainListSerializer):
    """
    Utilisé pour GET /api/terrains/:id/ (page détail).
    Ajoute tout ce qui n'est pas nécessaire dans la liste : capacité,
    horaires, la liste complète des photos, etc.
    """

    photos = TerrainPhotoSerializer(many=True, read_only=True)

    class Meta(TerrainListSerializer.Meta):
        fields = TerrainListSerializer.Meta.fields + [
            'capacite', 'photos', 'gerant',
        ]


class TerrainCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/terrains/ et PATCH /api/terrains/:id/.

    On ne gère PAS les photos ici : avec des fichiers (multipart/form-data),
    c'est plus simple et plus clair de les traiter à la main dans la vue.
    """

    class Meta:
        model = Terrain
        fields = [
            'nom', 'type', 'ville', 'adresse', 'capacite', 'surface',
            'prix_heure', 'avance', 'heure_ouverture', 'heure_fermeture',
            'equipements', 'description',
        ]
        # NB : "actif" n'est pas modifiable ici volontairement (pas de route
        # prévue pour ça dans la spec). Un nouveau terrain est actif par
        # défaut (voir Terrain.actif dans models.py).
