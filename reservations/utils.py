from creneaux.models import Creneau

from .models import Reservation


def liberer_si_expiree(reservation):
    """
    Si cette réservation est en attente de paiement depuis plus de 15
    minutes, on l'annule et on libère le créneau pour qu'il redevienne
    réservable par quelqu'un d'autre.

    On ne fait pas ça avec une tâche planifiée (Celery, etc.) pour rester
    simple : on vérifie juste à chaque fois qu'on lit une réservation.
    """
    if not reservation.est_expiree():
        return reservation

    reservation.statut = Reservation.Statut.ANNULEE
    reservation.save()

    creneau = reservation.creneau
    creneau.statut = Creneau.Statut.DISPONIBLE
    creneau.save()

    return reservation


def liberer_les_expirees(queryset):
    """Applique liberer_si_expiree() à toute une liste de réservations."""
    for reservation in queryset:
        liberer_si_expiree(reservation)
    return queryset
