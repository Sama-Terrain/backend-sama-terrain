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


class Employe(models.Model):
    """
    Un employé (gestionnaire sur place, caissier...) qui travaille pour un
    gérant propriétaire. Son compte User a le rôle "employe" et sa propre
    connexion : le propriétaire n'a plus à partager son mot de passe.

    Il accède aux terrains de son employeur pour le quotidien (réservations,
    scan des tickets, créneaux), mais jamais à l'argent (revenus,
    portefeuille, retraits) ni à l'abonnement. Pour le désactiver, on passe
    son compte à is_active=False : l'historique de ses actions est conservé.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profil_employe',
    )
    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employes',
    )
    ajoute_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} (employé de {self.proprietaire.email})"


class JournalAction(models.Model):
    """
    Journal d'activité de l'équipe d'un gérant : qui a fait quoi, et quand.
    Visible uniquement par le propriétaire.

    Les actions sur les créneaux arrivent par dizaines (la grille de tarifs
    crée/modifie un créneau par jour et par heure) : elles sont regroupées en
    une seule ligne "N créneaux modifiés sur X" tant que la même personne
    continue la même action sur le même terrain (voir gerant.equipe).
    """

    class Action(models.TextChoices):
        TICKET_VALIDE = 'ticket_valide', "Ticket validé"
        SOLDE_ENCAISSE = 'solde_encaisse', "Solde encaissé"
        RESERVATION_ANNULEE = 'reservation_annulee', "Réservation annulée"
        CRENEAUX_CREES = 'creneaux_crees', "Créneaux créés"
        CRENEAUX_MODIFIES = 'creneaux_modifies', "Créneaux modifiés"
        CRENEAUX_SUPPRIMES = 'creneaux_supprimes', "Créneaux supprimés"
        EMPLOYE_AJOUTE = 'employe_ajoute', "Employé ajouté"
        EMPLOYE_DESACTIVE = 'employe_desactive', "Employé désactivé"
        EMPLOYE_REACTIVE = 'employe_reactive', "Employé réactivé"

    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='journal_equipe',
    )
    # SET_NULL + nom copié : la ligne reste lisible même si le compte disparaît.
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+',
    )
    auteur_nom = models.CharField(max_length=310)
    action = models.CharField(max_length=25, choices=Action.choices)
    description = models.CharField(max_length=500)

    # Pour les actions regroupées (créneaux) : le terrain concerné et le nombre d'éléments.
    cible = models.CharField(max_length=150, blank=True)
    nombre = models.PositiveIntegerField(default=1)

    cree_le = models.DateTimeField(auto_now_add=True)
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-mis_a_jour_le']
        indexes = [models.Index(fields=['proprietaire', '-mis_a_jour_le'])]

    def __str__(self):
        return f"{self.auteur_nom} : {self.description}"
