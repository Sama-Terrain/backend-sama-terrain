import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission, IsAuthenticated

from paiements.models import Abonnement

from .equipe import proprietaire_de


class EstGerant(IsAuthenticated):
    """Autorise uniquement les utilisateurs connectés avec le rôle 'gerant'."""

    # has_permission est une méthode qui vérifie si l'utilisateur connecté a le rôle 'gerant'.
    # Elle retourne True si l'utilisateur est authentifié et a le rôle 'gerant', sinon elle retourne False.
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'gerant'


class EstGerantAbonnementActif(EstGerant):
    """
    Comme EstGerant, mais bloque en plus l'accès si l'abonnement du gérant
    est expiré (essai dépassé, ou abonnement payé dont la date de fin est
    passée). À utiliser sur les vues de l'espace gérant qui ne doivent être
    accessibles qu'avec un abonnement en cours — pas sur la page
    "Abonnement" elle-même, qui doit rester consultable (et payable) même
    une fois expirée.
    """

    message = "Votre abonnement a expiré. Veuillez le renouveler pour accéder à votre espace gérant."

    # has_permission est une méthode qui vérifie si l'utilisateur connecté a le rôle 'gerant' et si son abonnement est actif.
    # Elle retourne True si l'utilisateur est authentifié, a le rôle 'gerant' et son abonnement est actif, sinon elle retourne False.
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        # On récupère l'abonnement du gérant connecté (ou on le crée s'il n'existe pas encore) et on vérifie s'il est actif.
        # le _ veut dire qu'on ne se soucie pas de la valeur retournée par get_or_create() (True si créé, False si existait déjà) : on veut juste l'objet Abonnement.
        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif


class EstMembreEquipe(IsAuthenticated):
    """
    Le gérant propriétaire OU l'un de ses employés : pour le quotidien de
    l'espace gérant (réservations, tickets, créneaux). Les pages liées à
    l'argent et à l'abonnement restent réservées au propriétaire (EstGerant).
    """

    def has_permission(self, request, view):
        return super().has_permission(request, view) and proprietaire_de(request.user) is not None


class EstMembreEquipeAbonnementActif(EstMembreEquipe):
    """Comme EstMembreEquipe, avec l'abonnement du PROPRIÉTAIRE en cours."""

    message = EstGerantAbonnementActif.message

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        abonnement, _ = Abonnement.objects.get_or_create(gerant=proprietaire_de(request.user))
        return abonnement.est_actif


class EstN8n(BasePermission):
    """
    Appel serveur à serveur depuis N8n : autorisé seulement si l'en-tête
    X-N8N-Token correspond au jeton N8N_API_TOKEN configuré. Si aucun jeton
    n'est configuré, tout accès est refusé (jamais ouvert par défaut).
    """

    def has_permission(self, request, view):
        jeton_attendu = settings.N8N_API_TOKEN
        jeton_recu = request.headers.get('X-N8N-Token', '')
        return bool(jeton_attendu) and hmac.compare_digest(jeton_recu, jeton_attendu)
