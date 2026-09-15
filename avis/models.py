from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from reservations.models import Reservation
from terrains.models import Terrain


class Avis(models.Model):
    """
    Un avis laissé par un amateur sur un terrain, après avoir joué.

    Chaque avis est lié à UNE réservation précise (OneToOne) : ça garantit
    qu'on ne peut laisser un avis que si on a vraiment réservé et joué,
    et qu'on ne peut pas laisser plusieurs avis pour le même match.
    """

    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name='avis')
    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE, related_name='avis')
    amateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='avis')

    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.TextField(blank=True)

    # Un utilisateur peut signaler un avis qu'il juge abusif/faux.
    signale = models.BooleanField(default=False)

    # Un admin peut masquer un avis signalé : il n'apparaît alors plus
    # publiquement, mais reste en base (pas de suppression définitive).
    visible = models.BooleanField(default=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Avis {self.note}/5 - {self.terrain.nom} par {self.amateur.email}"
