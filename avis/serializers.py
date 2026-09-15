from django.utils import timezone
from rest_framework import serializers

from reservations.models import Reservation

from .models import Avis


def match_deja_joue(reservation):
    """True si l'heure de fin du créneau réservé est déjà passée."""
    fin_match = timezone.make_aware(
        timezone.datetime.combine(reservation.creneau.date, reservation.creneau.heure_fin)
    )
    return timezone.now() > fin_match


class AvisSerializer(serializers.ModelSerializer):
    """Représentation publique d'un avis (affiché sur la fiche terrain)."""

    nom = serializers.CharField(source='amateur.prenom', read_only=True)
    initiales = serializers.SerializerMethodField()

    class Meta:
        model = Avis
        fields = ['id', 'nom', 'initiales', 'note', 'commentaire', 'cree_le', 'signale']

    def get_initiales(self, avis):
        return f"{avis.amateur.prenom[:1]}{avis.amateur.nom[:1]}".upper()


class MeilleurAvisSerializer(AvisSerializer):
    """
    Représentation d'un avis pour la section témoignages de la page
    d'accueil (tous terrains confondus) : ajoute le nom du terrain, faute
    de rôle/fonction déclaré par l'amateur.
    """

    terrain = serializers.CharField(source='terrain.nom', read_only=True)

    class Meta(AvisSerializer.Meta):
        fields = AvisSerializer.Meta.fields + ['terrain']


class AvisCreateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/avis/.

    On ne demande que "reservation", "note" et "commentaire" : le terrain
    et l'amateur sont déduits automatiquement de la réservation.
    """

    class Meta:
        model = Avis
        fields = ['reservation', 'note', 'commentaire']

    def validate_reservation(self, reservation):
        request = self.context['request']

        if reservation.amateur_id != request.user.id:
            raise serializers.ValidationError("Cette réservation ne vous appartient pas.")

        if reservation.statut != Reservation.Statut.CONFIRMEE:
            raise serializers.ValidationError("Seules les réservations confirmées peuvent être notées.")

        if not match_deja_joue(reservation):
            raise serializers.ValidationError("Vous ne pouvez noter qu'après avoir joué.")

        if Avis.objects.filter(reservation=reservation).exists():
            raise serializers.ValidationError("Vous avez déjà laissé un avis pour cette réservation.")

        return reservation

    def create(self, validated_data):
        reservation = validated_data['reservation']
        return Avis.objects.create(
            terrain=reservation.creneau.terrain,
            amateur=reservation.amateur,
            **validated_data,
        )
