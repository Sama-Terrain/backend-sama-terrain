from django.conf import settings
from django.db import models
from django.utils import timezone

from reservations.models import Reservation

PRIX_ABONNEMENT_MENSUEL = 7500  # FCFA, montant fixe de la spec


class Abonnement(models.Model):
    """
    L'abonnement d'un gérant à la plateforme.

    Cycle de vie : à l'inscription, en attente de validation par l'admin.
    Une fois validé -> 7 jours d'essai gratuit. Après l'essai -> le gérant
    doit payer 7 500 FCFA/mois (voir AbonnementInitierView plus bas) pour
    garder l'accès actif.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE_VALIDATION = 'en_attente_validation', "En attente de validation admin"
        ESSAI = 'essai', "Période d'essai"
        ACTIF = 'actif', "Actif (payé)"
        EXPIRE = 'expire', "Expiré"

    gerant = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='abonnement',
    )

    statut = models.CharField(max_length=25, choices=Statut.choices, default=Statut.EN_ATTENTE_VALIDATION)

    # Rempli quand l'admin valide le gérant.
    date_fin_essai = models.DateTimeField(null=True, blank=True)

    # Rempli/étendu à chaque paiement d'abonnement réussi (+30 jours).
    date_fin_abonnement = models.DateTimeField(null=True, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    # Passe à True dès qu'une alerte d'expiration proche a été envoyée via
    # N8n, pour ne jamais l'envoyer deux fois pour la même échéance.
    alerte_expiration_envoyee = models.BooleanField(default=False)

    def __str__(self):
        return f"Abonnement de {self.gerant.email} ({self.statut})"

    @property
    def est_actif(self):
        """
        True si le gérant a encore accès à son espace : en essai avec une
        date de fin d'essai non dépassée, ou abonnement payé avec une date
        de fin d'abonnement non dépassée. Le statut en base n'est pas mis
        à jour par une tâche planifiée, donc l'expiration se calcule ici
        à la volée à partir des dates.
        """
        maintenant = timezone.now()
        if self.statut == self.Statut.ESSAI:
            return bool(self.date_fin_essai and self.date_fin_essai > maintenant)
        if self.statut == self.Statut.ACTIF:
            return bool(self.date_fin_abonnement and self.date_fin_abonnement > maintenant)
        return False


class Paiement(models.Model):
    """
    Journal de tous les paiements effectués sur la plateforme (avance de
    réservation, solde payé sur place, abonnement gérant). Sert surtout à
    garder un historique consultable (ex: page "Historique paiements" du gérant).
    """

    class Type(models.TextChoices):
        AVANCE = 'avance', "Avance de réservation (PayTech)"
        SOLDE = 'solde', "Solde payé sur place"
        ABONNEMENT = 'abonnement', "Abonnement gérant (PayTech)"

    type = models.CharField(max_length=15, choices=Type.choices)

    # Une réservation (avance/solde) OU un abonnement, jamais les deux à la fois.
    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name='paiements', null=True, blank=True
    )
    abonnement = models.ForeignKey(
        Abonnement, on_delete=models.CASCADE, related_name='paiements', null=True, blank=True
    )

    montant = models.PositiveIntegerField()
    moyen_paiement = models.CharField(max_length=30, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Paiement {self.type} - {self.montant} FCFA"
