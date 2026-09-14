from rest_framework import serializers

from avis.models import Avis
from gerant.models import DemandeGerant


class DemandeGerantSerializer(serializers.ModelSerializer):
    """Une demande de gérant, avec les infos du compte associé."""

    email = serializers.EmailField(source='user.email', read_only=True)
    prenom = serializers.CharField(source='user.prenom', read_only=True)
    nom = serializers.CharField(source='user.nom', read_only=True)

    class Meta:
        model = DemandeGerant
        fields = [
            'id', 'email', 'prenom', 'nom', 'nom_complexe', 'quartier',
            'adresse', 'whatsapp', 'document', 'statut', 'cree_le',
        ]


class AdminAvisSerializer(serializers.ModelSerializer):
    """Un avis, vu depuis l'espace admin (modération)."""

    amateur_nom = serializers.SerializerMethodField()
    terrain_nom = serializers.CharField(source='terrain.nom', read_only=True)

    class Meta:
        model = Avis
        fields = [
            'id', 'amateur_nom', 'terrain_nom', 'note', 'commentaire',
            'signale', 'visible', 'cree_le',
        ]

    def get_amateur_nom(self, avis):
        return f"{avis.amateur.prenom} {avis.amateur.nom}"
