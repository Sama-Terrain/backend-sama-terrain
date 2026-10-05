import re

from rest_framework import serializers

from .models import Portefeuille, Retrait

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


class PortefeuilleSerializer(serializers.ModelSerializer):
    """Le numéro Wave / Orange Money sur lequel le gérant reçoit son argent."""

    class Meta:
        model = Portefeuille
        fields = ['operateur', 'numero']

    def validate_numero(self, value):
        # Même règle que le téléphone du profil : mobile sénégalais, indicatif 221 inclus.
        numero = re.sub(r'\D', '', value)
        if not re.fullmatch(r'221(70|75|76|77|78)\d{7}', numero):
            raise serializers.ValidationError(
                "Numéro invalide : 9 chiffres commençant par 70, 75, 76, 77 ou 78."
            )
        return numero


class RetraitSerializer(serializers.ModelSerializer):
    operateur_libelle = serializers.CharField(source='get_operateur_display', read_only=True)
    gerant_nom = serializers.SerializerMethodField()
    gerant_email = serializers.EmailField(source='gerant.email', read_only=True)

    class Meta:
        model = Retrait
        fields = [
            'id', 'montant', 'operateur', 'operateur_libelle', 'numero', 'statut', 'methode',
            'reference_transaction', 'motif_echec', 'cree_le', 'traite_le', 'gerant_nom', 'gerant_email',
        ]
        read_only_fields = fields

    def get_gerant_nom(self, retrait):
        return f"{retrait.gerant.prenom} {retrait.gerant.nom}".strip()


class DemandeRetraitSerializer(serializers.Serializer):
    montant = serializers.IntegerField(min_value=1)
