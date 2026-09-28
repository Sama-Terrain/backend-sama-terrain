from rest_framework.permissions import IsAuthenticated

from paiements.models import Abonnement


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
