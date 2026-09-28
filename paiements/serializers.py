from rest_framework import serializers

from reservations.models import Commande, Reservation


class InitierPaiementSerializer(serializers.Serializer):
    """Vérifie qu'une réservation existe, appartient bien à l'amateur, et attend un paiement."""

    # On ne demande que l'identifiant de la réservation et le moyen de paiement choisi par l'amateur.
    reservation = serializers.PrimaryKeyRelatedField(queryset=Reservation.objects.all())

    # Le moyen déjà choisi par l'amateur dans notre interface (PaiementMethode.jsx) :
    # on le transmet à PayTech pour l'envoyer directement sur la bonne page de
    # paiement, sans lui refaire choisir un moyen de paiement.
    moyen_paiement = serializers.ChoiceField(choices=['Wave', 'Orange Money'])

    def validate_reservation(self, reservation):
        request = self.context['request']
        if reservation.amateur_id != request.user.id:
            raise serializers.ValidationError("Cette réservation ne vous appartient pas.")
        if reservation.statut != Reservation.Statut.EN_ATTENTE:
            raise serializers.ValidationError("Cette réservation n'attend pas de paiement.")
        return reservation


class InitierPaiementGroupeSerializer(serializers.Serializer):
    """
    Vérifie qu'une commande (plusieurs créneaux réservés ensemble) existe,
    appartient bien à l'amateur, et a au moins une réservation qui attend
    encore un paiement.
    """

    commande = serializers.PrimaryKeyRelatedField(queryset=Commande.objects.all())
    moyen_paiement = serializers.ChoiceField(choices=['Wave', 'Orange Money'])

    def validate_commande(self, commande):
        request = self.context['request']
        if commande.amateur_id != request.user.id:
            raise serializers.ValidationError("Cette commande ne vous appartient pas.")
        if not commande.reservations.filter(statut=Reservation.Statut.EN_ATTENTE).exists():
            raise serializers.ValidationError("Cette commande n'attend pas de paiement.")
        return commande


class SoldeSerializer(serializers.Serializer):
    """Utilisé pour enregistrer le paiement du solde restant, payé sur place."""

    #PrimaryKeyRelatedField est utilisé pour valider que la réservation existe et appartient bien à l'amateur connecté.
    reservation = serializers.PrimaryKeyRelatedField(queryset=Reservation.objects.all())
    moyen_paiement = serializers.ChoiceField(choices=['cash', 'wave', 'orange_money'])

    def validate_reservation(self, reservation):
        request = self.context['request']
        if reservation.creneau.terrain.gerant_id != request.user.id:
            raise serializers.ValidationError("Cette réservation ne concerne pas un de vos terrains.")
        if reservation.statut != Reservation.Statut.CONFIRMEE:
            raise serializers.ValidationError("Cette réservation n'est pas confirmée.")
        return reservation
