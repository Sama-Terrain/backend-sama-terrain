from rest_framework.permissions import BasePermission


class EstAdmin(BasePermission):
    """Autorise uniquement les utilisateurs avec le rôle 'admin'."""

    # has_permission est une méthode qui vérifie si l'utilisateur connecté a le rôle 'admin'.
    # Elle retourne True si l'utilisateur est authentifié et a le rôle 'admin', sinon elle retourne False.
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')
