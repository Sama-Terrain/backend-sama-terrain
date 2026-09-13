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
    ticket = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'statut', 'nom_complet', 'telephone',
            'montant_avance', 'montant_total', 'reste_a_payer',
            'moyen_paiement', 'transaction_id', 'cree_le',
            'terrain_id', 'terrain_nom', 'date', 'heure_debut', 'heure_fin',
            'ticket',
        ]

    def get_ticket(self, reservation):
        # Le ticket n'existe qu'une fois le paiement confirmé par l'IPN
        # (voir PaiementIPNView) : pas de ticket tant que c'est "en_attente".
        ticket = getattr(reservation, 'ticket', None)
        if ticket is None:
            return None
        return {'id': ticket.id, 'code': str(ticket.code), 'utilise': ticket.utilise}


MONTANT_AVANCE_MINIMUM = 10000


class ReservationCreateSerializer(serializers.ModelSerializer):
    """
    Utilisé pour POST /api/reservations/.

    L'amateur choisit lui-même le montant de son avance (doit être
    strictement supérieur à 10 000 FCFA) : ce n'est pas le gérant qui
    l'impose. Le reste (montant total, statut...) est déduit côté serveur.
    """

    class Meta:
        model = Reservation
        fields = ['creneau', 'nom_complet', 'telephone', 'montant_avance']

    def validate_creneau(self, creneau):
        if creneau.statut != Creneau.Statut.DISPONIBLE:
            raise serializers.ValidationError("Ce créneau n'est plus disponible.")
        return creneau

    def validate_montant_avance(self, montant):
        if montant <= MONTANT_AVANCE_MINIMUM:
            raise serializers.ValidationError(
                f"L'avance doit être strictement supérieure à {MONTANT_AVANCE_MINIMUM:,} FCFA.".replace(',', ' ')
            )
        return montant

    def validate(self, data):
        # L'avance ne peut pas dépasser le prix total du créneau (sinon le
        # "reste à payer sur place" deviendrait négatif).
        if data['montant_avance'] >= data['creneau'].prix:
            raise serializers.ValidationError(
                {'montant_avance': "L'avance ne peut pas être supérieure ou égale au prix total du créneau."}
            )
        return data

    def create(self, validated_data):
        creneau = validated_data['creneau']

        reservation = Reservation.objects.create(
            amateur=self.context['request'].user,
            montant_total=creneau.prix,
            **validated_data,
        )

        # On bloque immédiatement le créneau pour que personne d'autre
        # ne puisse le réserver pendant que le paiement est en cours.
        creneau.statut = Creneau.Statut.EN_ATTENTE
        creneau.save()

        return reservation
