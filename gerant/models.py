from django.conf import settings
from django.db import models


class DemandeGerant(models.Model):
    """
    La demande soumise par quelqu'un qui veut devenir gérant (formulaire
    "Devenir gérant" du frontend). Contient les infos business qu'un
    admin doit vérifier avant d'autoriser le compte.

    Le compte User est créé tout de suite (voir authentification), mais
    reste `is_active=False` tant que cette demande n'est pas validée.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', "En attente"
        VALIDEE = 'validee', "Validée"
        REJETEE = 'rejetee', "Rejetée"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='demande_gerant',
    )

    nom_complexe = models.CharField(max_length=150)
    quartier = models.CharField(max_length=100)
    adresse = models.CharField(max_length=255)
    whatsapp = models.CharField(max_length=20)

    # Le document justificatif (registre de commerce, CNI...) fourni pour la vérification.
    document = models.FileField(upload_to='demandes_gerant/')

    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.EN_ATTENTE)

    cree_le = models.DateTimeField(auto_now_add=True)
    traitee_le = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Demande de {self.user.email} ({self.statut})"
