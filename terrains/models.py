from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Terrain(models.Model):
    """
    Un terrain de mini-foot publié par un gérant.

    Les choix (TYPES, SURFACES) reprennent exactement les listes utilisées
    dans le formulaire du frontend (AjouterTerrain.jsx), pour que les valeurs
    envoyées par le frontend correspondent toujours à un choix valide.

    La ville, elle, n'est volontairement PAS une liste fermée (`choices`) :
    la liste de quartiers du frontend (voir frontend/src/utils/villes.js)
    évolue régulièrement, et un `choices` figé ici obligerait à resynchroniser
    les deux côtés à chaque ajout — ce qui a déjà cassé la création de
    terrain une fois. Un simple CharField laisse passer n'importe quelle
    valeur envoyée par le frontend, qui reste la seule source de vérité
    pour la liste affichée aux gérants.
    """

    TYPES = [
        ('Foot à 5', 'Foot à 5'),
        ('Foot à 6', 'Foot à 6'),
        ('Foot à 7', 'Foot à 7'),
        ('Foot à 11', 'Foot à 11'),
    ]

    SURFACES = [
        ('Synthétique', 'Synthétique'),
        ('Gazon naturel', 'Gazon naturel'),
        ('Bitume', 'Bitume'),
    ]

    # Le gérant propriétaire de ce terrain. Si le gérant est supprimé, ses
    # terrains sont supprimés aussi (on ne veut pas de terrain "orphelin").
    gerant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='terrains',
        limit_choices_to={'role': 'gerant'}, #limite les choix possibles à ceux dont le rôle est "gerant" (pour éviter d'associer un terrain à un amateur ou un admin).
    )

    nom = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=TYPES)
    ville = models.CharField(max_length=100)
    # Ancienne adresse écrite : n'est plus demandée au gérant (remplacée par
    # la position GPS), conservée pour les terrains créés avant.
    adresse = models.CharField(max_length=255, blank=True, default='')

    # Position GPS exacte du terrain, obligatoire à la création (voir
    # TerrainCreateUpdateSerializer). L'adresse écrite est souvent imprécise
    # à Dakar : avec ces coordonnées, le joueur voit le terrain sur une
    # carte et peut lancer un itinéraire. Nullable seulement pour les
    # terrains créés avant que la position soit obligatoire.
    # 6 décimales = précision d'environ 10 cm, largement suffisant.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    capacite = models.PositiveIntegerField(help_text="Nombre de joueurs")
    surface = models.CharField(max_length=20, choices=SURFACES)

    # Prix affiché au public, et montant de l'avance à payer pour réserver.
    prix_heure = models.PositiveIntegerField(help_text="Prix en FCFA par heure")
    avance = models.PositiveIntegerField(default=5000, help_text="Avance à payer en FCFA")

    # Un grand terrain peut être découpé en portions louées séparément
    # (ex: 3 petits matchs en même temps au lieu d'un grand).
    # 1 = terrain simple, non divisible (valeur de tous les anciens terrains).
    # 3 = on peut louer le terrain complet OU chacune de ses 3 portions.
    nombre_portions = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="1 = terrain simple ; 2 à 6 = terrain divisible en autant de portions",
    )

    # Prix d'UNE portion pour une heure, choisi par le gérant (ex: terrain
    # complet 60 000 FCFA, chaque portion 30 000 FCFA). Obligatoire pour un
    # terrain divisible, inutilisé pour un terrain simple.
    prix_portion = models.PositiveIntegerField(
        null=True, blank=True, help_text="Prix d'une portion en FCFA par heure (terrain divisible)",
    )

    heure_ouverture = models.TimeField(default='08:00')
    heure_fermeture = models.TimeField(default='23:00')

    # Liste de textes simples, ex: ["Vestiaires", "Éclairage nocturne"].
    # Une JSONField est le moyen le plus simple de stocker une liste en base.
    equipements = models.JSONField(default=list, blank=True)

    description = models.TextField(blank=True)

    # Un terrain inactif n'apparaît plus dans le catalogue public.
    actif = models.BooleanField(default=True)

    # Ces deux champs seront mis à jour automatiquement par l'app "avis"
    # à chaque nouvel avis (on ne les calcule pas à la volée pour rester simple).
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    nombre_avis = models.PositiveIntegerField(default=0)

    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} ({self.ville})"


class TerrainPhoto(models.Model):
    """Une photo appartenant à un terrain (un terrain peut en avoir plusieurs)."""

    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='terrains/')

    def __str__(self):
        return f"Photo de {self.terrain.nom}"
