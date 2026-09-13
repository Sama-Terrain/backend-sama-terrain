from rest_framework.permissions import SAFE_METHODS, BasePermission


class EstGerantOuLectureSeule(BasePermission):
    """
    Tout le monde peut lire (GET) la liste et le détail des terrains.
    Seul un utilisateur avec le rôle "gerant" peut créer un terrain (POST).
    """

    def has_permission(self, request, view):
        # SAFE_METHODS = GET, HEAD, OPTIONS : toujours autorisés.
        if request.method in SAFE_METHODS:
            return True

        return bool(request.user and request.user.is_authenticated and request.user.role == 'gerant')


class EstProprietaireDuTerrain(BasePermission):
    """
    Pour modifier (PATCH) ou supprimer (DELETE) un terrain précis, il faut
    être le gérant qui a créé CE terrain (pas juste "être gérant").
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        return obj.gerant_id == request.user.id
