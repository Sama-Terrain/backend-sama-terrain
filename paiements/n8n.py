import requests
from django.conf import settings


def notifier_n8n(evenement, donnees):
    """
    Envoie un évènement à N8n (email + WhatsApp automatiques).

    On ne fait qu'envoyer les données : c'est N8n, de son côté, qui décide
    quoi faire avec (quel email envoyer, à qui, etc.). Le backend Django
    n'a pas besoin de connaître ces détails.

    Si N8n est injoignable, on ne bloque pas le paiement pour autant :
    on log juste l'erreur (le paiement, lui, a déjà réussi).
    """
    if not settings.N8N_WEBHOOK_URL:
        return

    try:
        requests.post(
            settings.N8N_WEBHOOK_URL,
            json={'evenement': evenement, **donnees},
            timeout=5,
        )
    except requests.RequestException:
        # On n'interrompt jamais un paiement à cause d'une notification qui échoue.
        pass
