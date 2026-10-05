"""
Création et nettoyage des notifications de la cloche.

Ces fonctions s'appellent À CÔTÉ de notifier_n8n() (qui reste inchangé) :
N8n envoie les emails / WhatsApp, la base garde les notifications affichées
dans l'application.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Notification

# Les notifications déjà lues depuis plus longtemps que ça sont supprimées.
DUREE_CONSERVATION_LUES_JOURS = 90


def notifier(destinataire, type, titre, message, lien=''):
    """Crée une notification pour un utilisateur."""
    return Notification.objects.create(
        destinataire=destinataire, type=type, titre=titre, message=message, lien=lien,
    )


def notifier_admins(type, titre, message, lien=''):
    """Crée la même notification pour chaque administrateur actif."""
    User = get_user_model()
    admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
    Notification.objects.bulk_create([
        Notification(destinataire=admin, type=type, titre=titre, message=message, lien=lien)
        for admin in admins
    ])


def supprimer_anciennes_lues(destinataire=None):
    """
    Supprime les notifications lues depuis plus de 90 jours (toutes, ou
    seulement celles d'un utilisateur). Renvoie le nombre supprimé.
    Les notifications non lues sont toujours conservées.
    """
    limite = timezone.now() - timedelta(days=DUREE_CONSERVATION_LUES_JOURS)
    anciennes = Notification.objects.filter(lue=True, cree_le__lt=limite)
    if destinataire is not None:
        anciennes = anciennes.filter(destinataire=destinataire)
    nombre, _ = anciennes.delete()
    return nombre
