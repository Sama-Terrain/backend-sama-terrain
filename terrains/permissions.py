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
        # SAFE_METHODS est une constante fournie par Django REST Framework qui contient les méthodes HTTP considérées comme "sûres" (c'est-à-dire qui ne modifient pas les données), à savoir GET, HEAD et OPTIONS. Ces méthodes sont généralement utilisées pour lire des données sans les modifier.
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
        # on autorise toujours les méthodes SAFE_METHODS (GET, HEAD, OPTIONS) pour tout le monde, 
        # même si on n'est pas le propriétaire du terrain. Cela permet à n'importe quel utilisateur de voir les détails d'un terrain sans avoir besoin d'être le gérant qui l'a créé.
        if request.method in SAFE_METHODS:
            return True

        # Si l'utilisateur connecté n'est pas le gérant qui a créé le terrain, on refuse l'accès.
        # obj.gerant_id est l'identifiant du gérant qui a créé le terrain, et request.user.id est l'identifiant de l'utilisateur actuellement connecté.
        if obj.gerant_id != request.user.id:
            return False

        # Si l'utilisateur est bien le gérant du terrain, on vérifie que son abonnement est actif.
        abonnement, _ = Abonnement.objects.get_or_create(gerant=request.user)
        return abonnement.est_actif
