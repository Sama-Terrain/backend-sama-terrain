import hashlib
import hmac

import requests
from django.conf import settings


def creer_demande_paiement(
    item_name, item_price, ref_command, ipn_url, success_url, cancel_url, target_payment=None,
):
    """
    Demande à PayTech de créer un lien de paiement.

    PayTech répond avec une URL (`payment_url`) : c'est vers cette URL
    qu'on doit rediriger l'utilisateur pour qu'il paie avec Wave ou
    Orange Money. Une fois payé, PayTech appellera `ipn_url` de son côté.

    `target_payment` (ex: "Wave" ou "Orange Money") : si fourni, PayTech
    saute sa page de choix du moyen de paiement et envoie directement
    l'utilisateur sur la page de paiement de ce moyen-là (ex: le QR code
    Wave), puisqu'on lui a déjà fait ce choix dans notre interface.

    Retourne un dict {'payment_url': ..., 'token': ...} si tout va bien,
    ou lève une Exception si PayTech refuse la demande.
    """
    donnees_requete = {
        'item_name': item_name,
        'item_price': item_price,
        'currency': 'XOF',
        'ref_command': ref_command,
        'command_name': item_name,
        'ipn_url': ipn_url,
        'success_url': success_url,
        'cancel_url': cancel_url,
        'env': 'test',  # à passer à 'prod' une fois les vraies clés PayTech en place
    }

    # target_payment est optionnel : si on le fournit, PayTech ne demandera pas à l'utilisateur 
    # de choisir un moyen de paiement, mais l'enverra directement sur la page de paiement de ce moyen-là.
    if target_payment:
        donnees_requete['target_payment'] = target_payment

    reponse = requests.post(
        f"{settings.PAYTECH_BASE_URL}/payment/request-payment",
        headers={
            'API_KEY': settings.PAYTECH_API_KEY,
            'API_SECRET': settings.PAYTECH_API_SECRET,
        },
        data=donnees_requete,
        timeout=10,
    )
    reponse.raise_for_status()  # lève une exception si PayTech renvoie une erreur HTTP

    donnees = reponse.json()

    # Si PayTech refuse la demande, il renvoie un JSON avec un champ "error" : 
    # on lève une exception pour que le backend Django sache que ça a échoué.
    if 'error' in donnees:
        raise Exception(donnees['error'])

    return {
        'payment_url': donnees.get('redirect_url'),
        'token': donnees.get('token'),
    }


def ipn_authentique(donnees):
    """
    Vérifie qu'une notification IPN vient bien de PayTech : elle contient le
    SHA-256 de l'API key et de l'API secret de la plateforme (champs
    api_key_sha256 / api_secret_sha256). Sans cette vérification, n'importe
    qui pourrait appeler l'IPN et faire confirmer une réservation (ou
    activer un abonnement) sans avoir payé.
    """
    if not settings.PAYTECH_API_KEY or not settings.PAYTECH_API_SECRET:
        return False
    attendu_key = hashlib.sha256(settings.PAYTECH_API_KEY.encode()).hexdigest()
    attendu_secret = hashlib.sha256(settings.PAYTECH_API_SECRET.encode()).hexdigest()
    return (
        hmac.compare_digest(str(donnees.get('api_key_sha256', '')), attendu_key)
        and hmac.compare_digest(str(donnees.get('api_secret_sha256', '')), attendu_secret)
    )


def paiement_reussi(donnees):
    """PayTech appelle aussi l'IPN quand le paiement est annulé ("sale_canceled")."""
    return donnees.get('type_event', 'sale_complete') == 'sale_complete'
