from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from creneaux.models import Creneau

# Si le paiement de l'avance n'est pas confirmé dans ce délai, le créneau
# est automatiquement libéré (règle métier de la spec).
DELAI_EXPIRATION_MINUTES = 15

# Une annulation faite plus de 24h avant le match rembourse l'avance.
DELAI_REMBOURSEMENT_HEURES = 24


class Reservation(models.Model):
    """Une réservation d'un créneau par un amateur."""

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de paiement'
        CONFIRMEE = 'confirmee', 'Confirmée'
        TERMINEE = 'terminee', 'Terminée'
        ANNULEE = 'annulee', 'Annulée'

    amateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
    )

    # Le créneau réservé. Volontairement pas un OneToOne : si une réservation
    # est annulée, le créneau redevient disponible et peut être réservé
    # par quelqu'un d'autre plus tard (nouvelle Reservation, même Creneau).
    creneau = models.ForeignKey(Creneau, on_delete=models.CASCADE, related_name='reservations')

    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.EN_ATTENTE)

    # Coordonnées de la personne qui vient jouer (peut différer du compte
    # qui paie, ex: quelqu'un réserve pour son équipe).
    nom_complet = models.CharField(max_length=150)
    telephone = models.CharField(max_length=20)

    # On copie ces montants au moment de la création : si le gérant change
    # le prix du créneau après coup, ça ne doit pas changer cette réservation.
    montant_avance = models.PositiveIntegerField()
    montant_total = models.PositiveIntegerField()

    moyen_paiement = models.CharField(max_length=30, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    # Calculé à la création : cree_le + 15 minutes. Passé ce délai, si le
    # statut est toujours EN_ATTENTE, la réservation est considérée expirée.
    expire_le = models.DateTimeField()

    def save(self, *args, **kwargs):
        if self._state.adding and not self.expire_le:
            self.expire_le = timezone.now() + timedelta(minutes=DELAI_EXPIRATION_MINUTES)
        super().save(*args, **kwargs)

    @property
    def reste_a_payer(self):
        return self.montant_total - self.montant_avance

    def est_expiree(self):
        return self.statut == self.Statut.EN_ATTENTE and timezone.now() > self.expire_le

    def heures_avant_match(self):
        """Nombre d'heures entre maintenant et le début du créneau réservé."""
        debut_match = timezone.make_aware(
            timezone.datetime.combine(self.creneau.date, self.creneau.heure_debut)
        )
        return (debut_match - timezone.now()).total_seconds() / 3600

    def remboursement_possible(self):
        """True si une annulation maintenant rembourserait l'avance (règle des 24h)."""
        return self.heures_avant_match() >= DELAI_REMBOURSEMENT_HEURES

    def __str__(self):
        return f"Réservation {self.id} - {self.amateur.email} - {self.creneau}"
