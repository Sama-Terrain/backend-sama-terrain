from rest_framework import serializers

from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    """
    Représente un ticket. On y inclut les infos utiles de la réservation
    (client, terrain, créneau, montant restant) pour que le frontend
    n'ait pas besoin d'un deuxième appel pour les afficher.

    NB : `code` est la valeur à encoder dans le QR code affiché à l'écran
    (avec une librairie JS côté frontend, ex: react-qr-code) — le backend
    ne génère pas d'image, juste la valeur à encoder.
    """

    reservation = serializers.IntegerField(source='reservation.id', read_only=True)
    client = serializers.CharField(source='reservation.nom_complet', read_only=True)
    telephone = serializers.CharField(source='reservation.telephone', read_only=True)
    terrain = serializers.CharField(source='reservation.creneau.terrain.nom', read_only=True)
    date = serializers.DateField(source='reservation.creneau.date', read_only=True)
    heure_debut = serializers.TimeField(source='reservation.creneau.heure_debut', read_only=True)
    heure_fin = serializers.TimeField(source='reservation.creneau.heure_fin', read_only=True)
    montant_restant = serializers.IntegerField(source='reservation.reste_a_payer', read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'code', 'utilise', 'utilise_le', 'cree_le', 'reservation',
            'client', 'telephone', 'terrain', 'date', 'heure_debut', 'heure_fin',
            'montant_restant',
        ]


class ValiderTicketSerializer(serializers.Serializer):
    """Utilisé pour POST /api/tickets/valider/ : reçoit juste le code scanné."""

    code = serializers.UUIDField()

    def validate_code(self, value):
        ticket = Ticket.objects.filter(code=value).first()
        if ticket is None:
            raise serializers.ValidationError("Code de ticket invalide.")

        request = self.context['request']
        if ticket.reservation.creneau.terrain.gerant_id != request.user.id:
            raise serializers.ValidationError("Ce ticket ne concerne pas un de vos terrains.")

        if ticket.utilise:
            raise serializers.ValidationError("Ce ticket a déjà été utilisé.")

        self.ticket = ticket
        return value
