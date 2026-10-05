"""
Envoi de l'argent d'un retrait vers le Wave / Orange Money du gérant.

C'est le SEUL fichier à modifier pour passer de l'étape 1 à l'étape 2 :

- Étape 1, MODE_VERSEMENT = 'manuel' (actuel) : on ne fait rien ici. Le
  retrait reste "en attente" ; l'admin envoie l'argent lui-même depuis le
  compte de la plateforme, puis le marque comme versé (admin_panel).

- Étape 2, versement automatique : dans lancer_versement(), appeler l'API de
  paiement sortant du prestataire choisi (PayDunya, CinetPay, Wave Business...)
  avec retrait.montant / retrait.operateur / retrait.numero, enregistrer la
  référence renvoyée, puis appeler confirmer_versement() ou
  marquer_echec() quand le prestataire confirme (réponse directe ou webhook).
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notifier

from .n8n import notifier_n8n


def lancer_versement(retrait):
    if settings.MODE_VERSEMENT == 'manuel':
        return
    raise ImproperlyConfigured(f"MODE_VERSEMENT inconnu : {settings.MODE_VERSEMENT!r}")


def confirmer_versement(retrait, reference_transaction, traite_par=None):
    """L'argent est bien arrivé chez le gérant."""
    retrait.statut = retrait.Statut.VERSE
    retrait.reference_transaction = reference_transaction
    retrait.traite_le = timezone.now()
    retrait.traite_par = traite_par
    retrait.save()

    notifier_n8n('retrait_verse', {
        'email_gerant': retrait.gerant.email,
        'montant': retrait.montant,
        'operateur': retrait.get_operateur_display(),
        'numero': retrait.numero,
        'reference_transaction': reference_transaction,
    })

    notifier(
        retrait.gerant, Notification.Type.RETRAIT, 'Retrait versé',
        f"Votre retrait de {retrait.montant} FCFA a été envoyé sur votre {retrait.get_operateur_display()}.",
        '/gerant/portefeuille',
    )


def marquer_echec(retrait, motif, traite_par=None):
    """Versement impossible : le montant redevient disponible dans le solde du gérant."""
    retrait.statut = retrait.Statut.ECHOUE
    retrait.motif_echec = motif
    retrait.traite_le = timezone.now()
    retrait.traite_par = traite_par
    retrait.save()

    notifier_n8n('retrait_echoue', {
        'email_gerant': retrait.gerant.email,
        'montant': retrait.montant,
        'motif': motif,
    })

    notifier(
        retrait.gerant, Notification.Type.ALERTE, 'Retrait échoué',
        f"Votre retrait de {retrait.montant} FCFA n'a pas pu être versé : {motif}. Le montant est de nouveau disponible.",
        '/gerant/portefeuille',
    )
