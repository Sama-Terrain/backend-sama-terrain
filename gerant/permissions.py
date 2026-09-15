from rest_framework.permissions import IsAuthenticated

from paiements.models import Abonnement


class EstGerant(IsAuthenticated):
    """Autorise uniquement les utilisateurs connectés avec le rôle 'gerant'."""

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

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif
