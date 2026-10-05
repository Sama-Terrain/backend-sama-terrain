from django.utils import timezone
from rest_framework import serializers

from terrains.models import Terrain

from .models import Creneau


class CreneauSerializer(serializers.ModelSerializer):
    """Utilisé pour afficher un créneau (liste et détail)."""

    # "Terrain complet", "Portion 2"... (vide pour un terrain simple).
    libelle_portion = serializers.CharField(read_only=True)

    # Disponibilité RÉELLE, portions comprises : le terrain complet peut être
    # "disponible" en base mais non réservable si une portion est déjà prise.
    # C'est ce champ que le frontend doit utiliser pour l'affichage.
    disponible = serializers.SerializerMethodField()

    class Meta:
        model = Creneau
        fields = [
            'id', 'terrain', 'date', 'heure_debut', 'heure_fin',
            'prix', 'prix_recommande_ia', 'statut',
            'portion', 'libelle_portion', 'disponible',
        ]
        read_only_fields = ['statut', 'prix_recommande_ia', 'portion']

    def get_disponible(self, creneau):
        return creneau.est_reservable()


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

    def validate(self, data):
        # Un créneau déjà commencé ne pourrait de toute façon jamais être réservé.
        maintenant = timezone.localtime()
        if data['date'] < maintenant.date() or (
            data['date'] == maintenant.date() and data['heure_debut'] <= maintenant.time()
        ):
            raise serializers.ValidationError("Impossible de créer un créneau dans le passé.")

        # `portion` n'étant pas un champ du serializer, DRF ne vérifie pas le
        # unique_together du modèle : sans ce contrôle, un doublon ferait
        # planter la base (IntegrityError -> erreur 500).
        doublon = Creneau.objects.filter(
            terrain=data['terrain'], date=data['date'], heure_debut=data['heure_debut'], portion=0,
        ).exists()
        if doublon:
            raise serializers.ValidationError("Un créneau existe déjà à cette date et à cette heure pour ce terrain.")
        return data

    def create(self, validated_data):
        # Le gérant crée le créneau du terrain complet ; pour un terrain
        # divisible, les créneaux des portions sont créés automatiquement.
        creneau = super().create(validated_data)
        creneau.creer_ou_mettre_a_jour_portions()
        return creneau


class CreneauUpdateSerializer(serializers.ModelSerializer):
    """Utilisé pour PATCH /api/creneaux/:id/ (on ne change pas le terrain)."""

    class Meta:
        model = Creneau
        fields = ['date', 'heure_debut', 'heure_fin', 'prix']

    def validate(self, data):
        # Sur un terrain divisible, les portions sont rattachées au terrain
        # complet par leur date et leur heure : déplacer un seul de ces
        # créneaux casserait ce lien.
        creneau = self.instance
        change_horaire = (
            data.get('date', creneau.date) != creneau.date
            or data.get('heure_debut', creneau.heure_debut) != creneau.heure_debut
        )
        if change_horaire and creneau.terrain.nombre_portions > 1:
            raise serializers.ValidationError(
                "Sur un terrain divisible, supprimez ce créneau et recréez-le à la nouvelle date ou heure."
            )
        return data

    def update(self, instance, validated_data):
        # Si le prix du terrain complet change, celui des portions libres suit.
        creneau = super().update(instance, validated_data)
        creneau.creer_ou_mettre_a_jour_portions()
        return creneau
