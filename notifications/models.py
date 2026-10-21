from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    Notification affichée dans la cloche des espaces gérant et admin.

    Créée au moment de l'évènement (réservation payée, avis, retrait...),
    à côté de l'envoi à N8n qui, lui, s'occupe des emails / WhatsApp.
    L'état "lue" est stocké ici : il est donc le même sur tous les appareils.
    """

    class Type(models.TextChoices):
        RESERVATION = 'reservation', 'Nouvelle réservation'
        ANNULATION = 'annulation', 'Réservation annulée'
        AVIS = 'avis', 'Avis'
        RETRAIT = 'retrait', 'Retrait'
        ABONNEMENT = 'abonnement', 'Abonnement'
        ALERTE = 'alerte', 'Alerte'
        TERRAIN = 'terrain', 'Nouveau terrain'
        INSCRIPTION = 'inscription', 'Nouvelle inscription'

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
    )
    type = models.CharField(max_length=15, choices=Type.choices)
    titre = models.CharField(max_length=120)
    message = models.CharField(max_length=500)
    # Page du frontend ouverte au clic (ex: "/gerant/reservations?reservation=12").
    lien = models.CharField(max_length=255, blank=True)

    lue = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['destinataire', '-cree_le'])]

    def __str__(self):
        return f"{self.titre} → {self.destinataire.email}"
