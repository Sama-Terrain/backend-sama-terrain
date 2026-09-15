import uuid

from django.db import models

from reservations.models import Reservation


class Ticket(models.Model):
    """
    Le ticket QR remis à l'amateur une fois sa réservation payée et
    confirmée. Le gérant scanne ce QR code à l'entrée du terrain pour
    valider l'accès (voir POST /api/tickets/valider/).
    """

    # Une réservation confirmée = un seul ticket.
    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name='ticket')

    # Code unique et impossible à deviner, encodé dans le QR code.
    # C'est CE code (pas l'id numérique) qui doit être scanné/saisi.
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    utilise = models.BooleanField(default=False)
    utilise_le = models.DateTimeField(null=True, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ticket {self.code} - {self.reservation}"
