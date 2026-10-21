from rest_framework.permissions import BasePermission

from gerant.equipe import proprietaire_de
from paiements.models import Abonnement


class EstGerantProprietaireDuTerrain(BasePermission):
    """
    Seul le gérant propriétaire du terrain concerné (ou l'un de ses employés)
    peut créer, modifier ou supprimer un créneau pour ce terrain, et seulement
    si l'abonnement du propriétaire est en cours (essai ou payé non expiré).
    """

    # has_permission est appelé avant la création d'un objet Creneau (POST /api/creneaux/), pour vérifier que l'utilisateur connecté est bien un gérant et que son abonnement est actif.
    def has_permission(self, request, view):
        # on vérifie que l'utilisateur est bien un gérant et que son abonnement est actif. 
        # Cela permet de s'assurer que seuls les gérants ayant un abonnement valide peuvent créer des créneaux pour leurs terrains.
        proprietaire = proprietaire_de(request.user)
        if proprietaire is None:
            return False

        # on vérifie que l'abonnement du propriétaire est actif. Si l'abonnement n'existe pas encore, il sera créé automatiquement avec get_or_create.
        abonnement, _ = Abonnement.objects.get_or_create(gerant=proprietaire)
        return abonnement.est_actif

    def has_object_permission(self, request, view, obj):
        # `obj` est un Creneau : on vérifie le gérant du terrain lié.
        return obj.terrain.gerant_id == proprietaire_de(request.user).id
