from rest_framework import serializers

from creneaux.models import Creneau

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer):
    """
    Représentation complète d'une réservation, avec les infos du terrain
    et du créneau directement inclues (le frontend n'a pas besoin de faire
    d'appels supplémentaires pour afficher une carte de réservation).
    """

    terrain_id = serializers.IntegerField(source='creneau.terrain.id', read_only=True)
    terrain_nom = serializers.CharField(source='creneau.terrain.nom', read_only=True)
    date = serializers.DateField(source='creneau.date', read_only=True)
    heure_debut = serializers.TimeField(source='creneau.heure_debut', read_only=True)
    heure_fin = serializers.TimeField(source='creneau.heure_fin', read_only=True)
    reste_a_payer = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id', 'statut', 'nom_complet', 'telephone',
            'montant_avance', 'montant_total', 'reste_a_payer',
            'moyen_paiement', 'transaction_id', 'cree_le',
            'terrain_id', 'terrain_nom', 'date', 'heure_debut', 'heure_fin',
        ]


class ReservationCreateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/reservations/.

    Ne demande que ce que l'amateur doit fournir : le créneau choisi et
    ses coordonnées. Le reste (montants, statut...) est déduit côté serveur.
    """

    class Meta:
        model = Reservation
        fields = ['creneau', 'nom_complet', 'telephone']

    def validate_creneau(self, creneau):
        if creneau.statut != Creneau.Statut.DISPONIBLE:
            raise serializers.ValidationError("Ce créneau n'est plus disponible.")
        return creneau

    def create(self, validated_data):
        creneau = validated_data['creneau']

        reservation = Reservation.objects.create(
            amateur=self.context['request'].user,
            montant_avance=creneau.terrain.avance,
            montant_total=creneau.prix,
            **validated_data,
        )

        # On bloque immédiatement le créneau pour que personne d'autre
        # ne puisse le réserver pendant que le paiement est en cours.
        creneau.statut = Creneau.Statut.EN_ATTENTE
        creneau.save()

        return reservation
