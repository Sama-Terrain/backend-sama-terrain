from rest_framework import serializers

from terrains.models import Terrain

from .models import Creneau


class CreneauSerializer(serializers.ModelSerializer):
    """Utilisé pour afficher un créneau (liste et détail)."""

    class Meta:
        model = Creneau
        fields = [
            'id', 'terrain', 'date', 'heure_debut', 'heure_fin',
            'prix', 'prix_recommande_ia', 'statut',
        ]
        read_only_fields = ['statut', 'prix_recommande_ia']


class CreneauCreateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/creneaux/.

    On vérifie ici que le terrain choisi appartient bien au gérant connecté
    (impossible via `permissions.py`, puisqu'on n'a pas encore d'objet Creneau
    à ce stade : on est en train de le créer).
    """

    class Meta:
        model = Creneau
        fields = ['terrain', 'date', 'heure_debut', 'heure_fin', 'prix']

    def validate_terrain(self, terrain):
        request = self.context['request']
        if terrain.gerant_id != request.user.id:
            raise serializers.ValidationError("Ce terrain ne vous appartient pas.")
        return terrain


class CreneauUpdateSerializer(serializers.ModelSerializer):
    """Utilisé pour PATCH /api/creneaux/:id/ (on ne change pas le terrain)."""

    class Meta:
        model = Creneau
        fields = ['date', 'heure_debut', 'heure_fin', 'prix']
