from rest_framework import serializers

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


# On applique liberer_si_expiree() à toute une liste de réservations.
def liberer_les_expirees(queryset):
    """Applique liberer_si_expiree() à toute une liste de réservations."""
    for reservation in queryset:
        liberer_si_expiree(reservation)
    return queryset


MESSAGE_CRENEAU_PRIS = (
    "Ce créneau n'est plus disponible : il est déjà réservé, ou une autre "
    "partie de ce terrain (portion ou terrain complet) est réservée à cette heure."
)


def bloquer_creneau(creneau):
    """
    Réserve le créneau pour le joueur (statut "en_attente" pendant le
    paiement), SEULEMENT s'il est encore réservable. Sinon, lève une erreur
    de validation (réponse 400 envoyée au frontend).

    Doit être appelée à l'intérieur d'un `transaction.atomic()`.

    Pourquoi un verrou ? Deux joueurs peuvent cliquer sur "Réserver" presque
    au même moment. select_for_update() verrouille les créneaux de ce
    terrain à cette date et cette heure (terrain complet ET portions)
    jusqu'à la fin de la transaction : la deuxième demande attend que la
    première soit terminée, puis voit que le créneau est déjà pris.
    """
    list(
        Creneau.objects.select_for_update().filter(
            terrain_id=creneau.terrain_id, date=creneau.date, heure_debut=creneau.heure_debut,
        )
    )

    # On relit le créneau APRÈS avoir obtenu le verrou : sa valeur a pu
    # changer pendant qu'on attendait.
    creneau.refresh_from_db()
    if not creneau.est_reservable():
        raise serializers.ValidationError({'creneau': [MESSAGE_CRENEAU_PRIS]})

    creneau.statut = Creneau.Statut.EN_ATTENTE
    creneau.save()
