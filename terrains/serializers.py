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
    #serializers.SerializerMethodField() est utilisé pour définir un champ personnalisé dans le serializer.
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
            creneau__date__gte=debut_mois, #gte signifie "greater than or equal to" (supérieur ou égal à). On ne compte que les réservations confirmées pour le mois en cours.
        ).count()

    def get_revenus_mois(self, terrain):
        if not self.context.get('stats_gerant'):
            return None
        debut_mois = timezone.localdate().replace(day=1)
        total = Paiement.objects.filter(
            reservation__creneau__terrain=terrain,
            cree_le__date__gte=debut_mois,
        ).aggregate(total=Sum('montant'))['total'] #aggregate permet de calculer des valeurs agrégées (comme la somme, la moyenne, le maximum, etc.) sur un queryset. Ici, on calcule la somme des montants des paiements pour le terrain donné depuis le début du mois.
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

    photos = TerrainPhotoSerializer(many=True, read_only=True) #many=True indique que le champ photos est une liste de plusieurs objets TerrainPhoto, et read_only=True signifie que ce champ ne peut pas être modifié via ce serializer (il est uniquement utilisé pour la lecture des données).

    # On hérite de TerrainListSerializer pour ne pas dupliquer le code des champs communs 
    # (nom, ville, adresse, type, surface, prix_heure, avance, note_moyenne, nombre_avis, 
    # actif, equipements, description, image, heure_ouverture, heure_fermeture, reservations_mois, revenus_mois, taux_occupation).
    # et on ajoute les champs spécifiques à la page détail (capacite, photos, gerant).
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

    # Fourchette de capacité plausible pour chaque type de terrain, déduite
    # directement du format annoncé par le type ("Foot à 5" = 5 joueurs par
    # équipe, donc 10 sur le terrain, plus quelques remplaçants). Même règle
    # appliquée côté frontend (voir AjouterTerrain.jsx).
    CAPACITE_PAR_TYPE = {
        'Foot à 5': (10, 14),
        'Foot à 6': (12, 16),
        'Foot à 7': (14, 18),
        'Foot à 11': (22, 30),
    }

    def validate_nom(self, value):
        if not value.strip():
            raise serializers.ValidationError("Le nom du terrain est obligatoire.")
        return value.strip()

    def validate_adresse(self, value):
        if not value.strip():
            raise serializers.ValidationError("L'adresse est obligatoire.")
        return value.strip()

    def validate_prix_heure(self, value):
        if value < 500:
            raise serializers.ValidationError("Le prix par heure doit être au moins 500 FCFA.")
        return value

    def validate(self, data):
        # Sur un PATCH partiel, un champ peut être absent de `data` : on va
        # chercher sa valeur actuelle sur l'instance existante pour comparer
        # les bonnes valeurs entre elles.
        type_terrain = data.get('type', getattr(self.instance, 'type', None))
        capacite = data.get('capacite', getattr(self.instance, 'capacite', None))

        if type_terrain and capacite is not None:
            bornes = self.CAPACITE_PAR_TYPE.get(type_terrain)
            if bornes and not (bornes[0] <= capacite <= bornes[1]):
                raise serializers.ValidationError({
                    'capacite': (
                        f"La capacité renseignée n'est pas compatible avec le type "
                        f"\"{type_terrain}\" (attendu : entre {bornes[0]} et {bornes[1]} joueurs)."
                    )
                })

        heure_ouverture = data.get('heure_ouverture', getattr(self.instance, 'heure_ouverture', None))
        heure_fermeture = data.get('heure_fermeture', getattr(self.instance, 'heure_fermeture', None))
        if heure_ouverture and heure_fermeture and heure_ouverture >= heure_fermeture:
            raise serializers.ValidationError({
                'heure_fermeture': "L'heure de fermeture doit être après l'heure d'ouverture.",
            })

        return data

