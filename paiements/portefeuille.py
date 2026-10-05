"""
Calcul du solde du portefeuille d'un gérant, et demandes de retrait.

Le solde se déduit de l'historique (jamais stocké) :

    solde disponible = avances débloquées - retraits (en attente ou versés)

Une avance n'est "débloquée" qu'à moins de 24h du match : avant, le joueur
peut encore annuler et être remboursé (voir Reservation.remboursement_possible).
Le gérant ne peut donc jamais retirer de l'argent qu'il faudrait rendre.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notifier_admins
from reservations.models import DELAI_REMBOURSEMENT_HEURES, Reservation

from .models import Paiement, Portefeuille, Retrait
from .versements import lancer_versement

MONTANT_RETRAIT_MINIMUM = 1000  # FCFA


class RetraitRefuse(Exception):
    """Demande de retrait impossible : le message est affiché au gérant."""


def _total(queryset):
    return queryset.aggregate(total=Sum('montant'))['total'] or 0


def _avances_du_gerant(gerant):
    """Avances payées sur ses terrains, hors celles remboursées au joueur."""
    rembourses = Paiement.objects.filter(type=Paiement.Type.REMBOURSEMENT).values('reservation_id')
    return Paiement.objects.filter(
        type=Paiement.Type.AVANCE,
        reservation__creneau__terrain__gerant=gerant,
    ).exclude(reservation_id__in=rembourses)


def _filtre_debloquees():
    """Avances dont le match commence dans moins de 24h (ou est passé) : plus remboursables."""
    limite = timezone.localtime() + timedelta(hours=DELAI_REMBOURSEMENT_HEURES)
    return Q(reservation__creneau__date__lt=limite.date()) | Q(
        reservation__creneau__date=limite.date(),
        reservation__creneau__heure_debut__lte=limite.time(),
    )


def etat_portefeuille(gerant):
    avances = _avances_du_gerant(gerant)
    debloquees = _total(avances.filter(_filtre_debloquees()))
    # Pas encore débloquées : réservations toujours actives, match dans plus de 24h.
    a_venir = _total(
        avances.exclude(_filtre_debloquees()).exclude(reservation__statut=Reservation.Statut.ANNULEE)
    )

    retraits = Retrait.objects.filter(gerant=gerant)
    en_cours = _total(retraits.filter(statut=Retrait.Statut.EN_ATTENTE))
    verse = _total(retraits.filter(statut=Retrait.Statut.VERSE))

    return {
        'solde_disponible': debloquees - en_cours - verse,
        'a_venir': a_venir,
        'en_cours_de_versement': en_cours,
        'total_verse': verse,
        'montant_retrait_minimum': MONTANT_RETRAIT_MINIMUM,
    }


def demander_retrait(gerant, montant):
    with transaction.atomic():
        # Verrou sur le portefeuille : deux demandes envoyées en même temps
        # (double clic...) ne peuvent pas retirer deux fois le même argent.
        portefeuille = Portefeuille.objects.select_for_update().filter(gerant=gerant).first()
        if portefeuille is None:
            raise RetraitRefuse("Ajoutez d'abord votre numéro Wave ou Orange Money.")

        if Retrait.objects.filter(gerant=gerant, statut=Retrait.Statut.EN_ATTENTE).exists():
            raise RetraitRefuse("Un retrait est déjà en cours de versement : attendez qu'il soit traité.")

        if montant < MONTANT_RETRAIT_MINIMUM:
            raise RetraitRefuse(f"Le montant minimum d'un retrait est de {MONTANT_RETRAIT_MINIMUM:,} FCFA.".replace(',', ' '))

        solde = etat_portefeuille(gerant)['solde_disponible']
        if montant > solde:
            raise RetraitRefuse(f"Montant supérieur à votre solde disponible ({solde:,} FCFA).".replace(',', ' '))

        retrait = Retrait.objects.create(
            gerant=gerant,
            montant=montant,
            operateur=portefeuille.operateur,
            numero=portefeuille.numero,
        )

    notifier_admins(
        Notification.Type.RETRAIT, 'Retrait à verser',
        f"{gerant.prenom} {gerant.nom} demande un retrait de {retrait.montant} FCFA "
        f"sur son {retrait.get_operateur_display()}.",
        '/admin/retraits',
    )

    lancer_versement(retrait)
    return retrait
