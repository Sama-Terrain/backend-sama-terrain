from rest_framework.permissions import SAFE_METHODS, BasePermission

from paiements.models import Abonnement


class EstGerantOuLectureSeule(BasePermission):
    """
    Tout le monde peut lire (GET) la liste et le détail des terrains.
    Seul un utilisateur avec le rôle "gerant" peut créer un terrain (POST),
    et seulement si son abonnement est en cours (essai ou payé non expiré).
    """

    def has_permission(self, request, view):
        # SAFE_METHODS = GET, HEAD, OPTIONS : toujours autorisés.
        if request.method in SAFE_METHODS:
            return True

        if not bool(request.user and request.user.is_authenticated and request.user.role == 'gerant'):
            return False

        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif


class EstProprietaireDuTerrain(BasePermission):
    """
    Pour modifier (PATCH) ou supprimer (DELETE) un terrain précis, il faut
    être le gérant qui a créé CE terrain (pas juste "être gérant"), et son
    abonnement doit être en cours.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        if obj.gerant_id != request.user.id:
            return False

        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif
