from rest_framework.permissions import BasePermission

from paiements.models import Abonnement


class EstGerantProprietaireDuTerrain(BasePermission):
    """
    Seul le gérant propriétaire du terrain concerné peut créer, modifier
    ou supprimer un créneau pour ce terrain, et seulement si son abonnement
    est en cours (essai ou payé non expiré).
    """

    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated and request.user.role == 'gerant'):
            return False

        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif

    def has_object_permission(self, request, view, obj):
        # `obj` est un Creneau : on vérifie le gérant du terrain lié.
        return obj.terrain.gerant_id == request.user.id
