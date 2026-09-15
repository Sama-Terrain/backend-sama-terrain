from django.db import models

from terrains.models import Terrain


class Creneau(models.Model):
    """
    Un créneau horaire réservable pour un terrain donné, à une date et
    une heure précises (ex: "Elite Arena, le 15/03/2026, 18h-19h").
    """

    class Statut(models.TextChoices):
        # Personne n'a réservé ce créneau, ou une réservation a expiré/été annulée.
        DISPONIBLE = 'disponible', 'Disponible'
        # Une réservation vient d'être créée, en attente du paiement de l'avance.
        EN_ATTENTE = 'en_attente', 'En attente de paiement'
        # Le paiement de l'avance a été confirmé par PayTech.
        CONFIRME = 'confirme', 'Confirmé'

    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE, related_name='creneaux')

    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()

    # Chaque créneau a son propre prix (permet au gérant de faire varier
    # les tarifs selon l'heure : prix week-end, heures de pointe, etc.)
    prix = models.PositiveIntegerField(help_text="Prix en FCFA")

    # Champs remplis par le service IA (FastAPI, voir /api/ia/predictions/)
    # à partir des vraies statistiques de réservation. Vides tant qu'aucune
    # analyse n'a encore été demandée pour ce terrain.
    class NiveauDemande(models.TextChoices):
        FAIBLE = 'faible', 'Faible'
        MOYEN = 'moyen', 'Moyen'
        ELEVE = 'eleve', 'Élevé'

    niveau_demande = models.CharField(
        max_length=10, choices=NiveauDemande.choices, null=True, blank=True,
    )
    prix_recommande_ia = models.PositiveIntegerField(null=True, blank=True)
    derniere_maj_ia = models.DateTimeField(null=True, blank=True)

    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.DISPONIBLE)

    class Meta:
        # Un terrain ne peut pas avoir deux fois le même créneau (même date + même heure).
        unique_together = ['terrain', 'date', 'heure_debut']
        ordering = ['date', 'heure_debut']

    def __str__(self):
        return f"{self.terrain.nom} - {self.date} {self.heure_debut}-{self.heure_fin}"
