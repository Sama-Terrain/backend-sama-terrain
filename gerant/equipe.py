"""
Équipe d'un gérant : le propriétaire des terrains et ses employés.

Toutes les données de l'espace gérant (terrains, créneaux, réservations,
tickets...) appartiennent au PROPRIÉTAIRE. Un employé y accède pour le compte
de son employeur : on passe donc toujours par proprietaire_de(user) au lieu
d'utiliser directement request.user.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import JournalAction

# Une même action répétée sur les créneaux d'un terrain (grille de tarifs)
# est fusionnée dans la même ligne du journal tant qu'il n'y a pas eu de
# pause de plus de 10 minutes.
DELAI_REGROUPEMENT = timedelta(minutes=10)

ACTIONS_REGROUPEES = {
    JournalAction.Action.CRENEAUX_CREES: 'créé',
    JournalAction.Action.CRENEAUX_MODIFIES: 'modifié',
    JournalAction.Action.CRENEAUX_SUPPRIMES: 'supprimé',
}


def proprietaire_de(user):
    """
    Le gérant pour le compte duquel `user` travaille : lui-même s'il est
    gérant, son employeur s'il est employé, None sinon (amateur, admin,
    visiteur, ou employé sans employeur).
    """
    if not user or not user.is_authenticated:
        return None
    if user.role == 'gerant':
        return user
    if user.role == 'employe':
        profil = getattr(user, 'profil_employe', None)
        return profil.proprietaire if profil else None
    return None


def est_proprietaire_de(user, gerant_id):
    """True si `user` (gérant ou employé) travaille pour le gérant `gerant_id`."""
    proprietaire = proprietaire_de(user)
    return proprietaire is not None and proprietaire.id == gerant_id


def membres_equipe(proprietaire):
    """Le propriétaire et ses employés actifs (pour les notifications)."""
    return get_user_model().objects.filter(
        Q(pk=proprietaire.pk) | Q(profil_employe__proprietaire=proprietaire), is_active=True,
    )


def journaliser(auteur, action, description='', cible=''):
    """
    Enregistre une action dans le journal de l'équipe de `auteur`.
    Ne fait rien si l'auteur n'appartient à aucune équipe (ex: un amateur
    qui annule sa propre réservation).
    """
    proprietaire = proprietaire_de(auteur)
    if proprietaire is None:
        return None

    auteur_nom = f"{auteur.prenom} {auteur.nom}"

    if action in ACTIONS_REGROUPEES:
        derniere = JournalAction.objects.filter(
            proprietaire=proprietaire, auteur=auteur, action=action, cible=cible,
            mis_a_jour_le__gte=timezone.now() - DELAI_REGROUPEMENT,
        ).first()
        if derniere:
            derniere.nombre += 1
            derniere.description = _texte_regroupe(action, derniere.nombre, cible)
            derniere.save(update_fields=['nombre', 'description', 'mis_a_jour_le'])
            return derniere
        description = _texte_regroupe(action, 1, cible)

    return JournalAction.objects.create(
        proprietaire=proprietaire, auteur=auteur, auteur_nom=auteur_nom,
        action=action, description=description, cible=cible,
    )


def _texte_regroupe(action, nombre, cible):
    verbe = ACTIONS_REGROUPEES[action]
    pluriel = 's' if nombre > 1 else ''
    return f"{nombre} créneau{'x' if nombre > 1 else ''} {verbe}{pluriel} sur {cible}"
