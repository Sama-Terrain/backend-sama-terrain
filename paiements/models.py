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

    # Méthodes utilitaires pour savoir si le gérant a encore accès à son espace
    # @property permet de l'utiliser comme un attribut (ex: abonnement.est_actif) plutôt qu'une méthode (ex: abonnement.est_actif()).
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
        # Avance rendue au joueur (annulation plus de 24h avant le match) :
        # elle ne revient donc pas au gérant (voir portefeuille.py).
        REMBOURSEMENT = 'remboursement', "Remboursement de l'avance (annulation)"

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

    # Pour le solde payé sur place : qui a encaissé l'argent (le gérant ou
    # l'un de ses employés). Vide pour les paiements en ligne (PayTech).
    encaisse_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Paiement {self.type} - {self.montant} FCFA"


class Operateur(models.TextChoices):
    """Les comptes mobile money sur lesquels un gérant peut recevoir son argent."""
    WAVE = 'wave', "Wave"
    ORANGE_MONEY = 'orange_money', "Orange Money"


class Portefeuille(models.Model):
    """
    Le "wallet" d'un gérant. Les avances payées par les joueurs arrivent
    sur le compte PayTech de la plateforme ; la plateforme les doit ensuite
    au gérant, qui les retire vers son numéro Wave ou Orange Money.

    Le solde n'est PAS stocké ici : il est recalculé à partir des paiements
    et des retraits (voir portefeuille.py), pour ne jamais être désynchronisé.
    Ce modèle ne garde que le numéro sur lequel verser l'argent.
    """

    gerant = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='portefeuille',
    )
    operateur = models.CharField(max_length=15, choices=Operateur.choices)
    # Format "221XXXXXXXXX", comme les autres téléphones de l'application.
    numero = models.CharField(max_length=12)
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Portefeuille de {self.gerant.email} ({self.get_operateur_display()} {self.numero})"


class Retrait(models.Model):
    """
    Une demande du gérant pour récupérer (une partie de) son solde.

    Étape 1 (actuelle) : l'admin envoie l'argent lui-même depuis le compte
    Wave/Orange Money de la plateforme, puis marque le retrait comme versé.
    Étape 2 (plus tard) : une API de paiement sortant fera le versement ;
    il suffira de brancher versements.py, ce modèle reste le même.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', "En attente de versement"
        VERSE = 'verse', "Versé"
        # Versement impossible (numéro erroné...) : le montant revient dans le solde.
        ECHOUE = 'echoue', "Échoué"

    class Methode(models.TextChoices):
        MANUELLE = 'manuelle', "Versement manuel par l'admin"
        AUTOMATIQUE = 'automatique', "Versement automatique (API)"

    gerant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='retraits')
    montant = models.PositiveIntegerField()

    # Copie du numéro au moment de la demande : si le gérant change de
    # numéro ensuite, on sait toujours où l'argent a été envoyé.
    operateur = models.CharField(max_length=15, choices=Operateur.choices)
    numero = models.CharField(max_length=12)

    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.EN_ATTENTE)
    methode = models.CharField(max_length=15, choices=Methode.choices, default=Methode.MANUELLE)

    # Identifiant de la transaction Wave/Orange Money (saisi par l'admin à
    # l'étape 1, renvoyé par l'API de versement à l'étape 2).
    reference_transaction = models.CharField(max_length=100, blank=True)
    motif_echec = models.CharField(max_length=255, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)
    traite_le = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['-cree_le']

    def __str__(self):
        return f"Retrait {self.montant} FCFA - {self.gerant.email} ({self.statut})"
