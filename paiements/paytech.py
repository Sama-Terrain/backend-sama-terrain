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
    return {
        'payment_url': donnees.get('redirect_url'),
        'token': donnees.get('token'),
    }
