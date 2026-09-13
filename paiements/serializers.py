from rest_framework import serializers

from reservations.models import Reservation


class InitierPaiementSerializer(serializers.Serializer):
    """Vérifie qu'une réservation existe, appartient bien à l'amateur, et attend un paiement."""

    reservation = serializers.PrimaryKeyRelatedField(queryset=Reservation.objects.all())

    def validate_reservation(self, reservation):
        request = self.context['request']
        if reservation.amateur_id != request.user.id:
            raise serializers.ValidationError("Cette réservation ne vous appartient pas.")
        if reservation.statut != Reservation.Statut.EN_ATTENTE:
            raise serializers.ValidationError("Cette réservation n'attend pas de paiement.")
        return reservation


class SoldeSerializer(serializers.Serializer):
    """Utilisé pour enregistrer le paiement du solde restant, payé sur place."""

    reservation = serializers.PrimaryKeyRelatedField(queryset=Reservation.objects.all())
    moyen_paiement = serializers.ChoiceField(choices=['cash', 'wave', 'orange_money'])

    def validate_reservation(self, reservation):
        request = self.context['request']
        if reservation.creneau.terrain.gerant_id != request.user.id:
            raise serializers.ValidationError("Cette réservation ne concerne pas un de vos terrains.")
        if reservation.statut != Reservation.Statut.CONFIRMEE:
            raise serializers.ValidationError("Cette réservation n'est pas confirmée.")
        return reservation
