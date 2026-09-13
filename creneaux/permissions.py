from rest_framework.permissions import BasePermission


class EstGerantProprietaireDuTerrain(BasePermission):
    """
    Seul le gérant propriétaire du terrain concerné peut créer, modifier
    ou supprimer un créneau pour ce terrain.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'gerant')

    def has_object_permission(self, request, view, obj):
        # `obj` est un Creneau : on vérifie le gérant du terrain lié.
        return obj.terrain.gerant_id == request.user.id
