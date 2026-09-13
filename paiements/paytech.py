import requests
from django.conf import settings


def creer_demande_paiement(item_name, item_price, ref_command, ipn_url, success_url, cancel_url):
    """
    Demande à PayTech de créer un lien de paiement.

    PayTech répond avec une URL (`payment_url`) : c'est vers cette URL
    qu'on doit rediriger l'utilisateur pour qu'il paie avec Wave ou
    Orange Money. Une fois payé, PayTech appellera `ipn_url` de son côté.

    Retourne un dict {'payment_url': ..., 'token': ...} si tout va bien,
    ou lève une Exception si PayTech refuse la demande.
    """
    reponse = requests.post(
        f"{settings.PAYTECH_BASE_URL}/payment/request-payment",
        headers={
            'API_KEY': settings.PAYTECH_API_KEY,
            'API_SECRET': settings.PAYTECH_API_SECRET,
        },
        data={
            'item_name': item_name,
            'item_price': item_price,
            'currency': 'XOF',
            'ref_command': ref_command,
            'command_name': item_name,
            'ipn_url': ipn_url,
            'success_url': success_url,
            'cancel_url': cancel_url,
            'env': 'test',  # à passer à 'prod' une fois les vraies clés PayTech en place
        },
        timeout=10,
    )
    reponse.raise_for_status()  # lève une exception si PayTech renvoie une erreur HTTP

    donnees = reponse.json()
    return {
        'payment_url': donnees.get('redirect_url'),
        'token': donnees.get('token'),
    }
