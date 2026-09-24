import random

from django.core.mail import send_mail
from django.utils import timezone


def generer_et_envoyer_code(user):
    """
    Génère un code à 6 chiffres pour `user`, le sauvegarde sur son compte,
    et l'envoie par email via Gmail (configuré dans settings.py).

    Utilisée après l'inscription, et aussi quand l'utilisateur demande
    un renvoi de code (POST /api/auth/resend-code).
    """
    # Un nombre aléatoire à 6 chiffres, toujours écrit sur 6 caractères
    # (ex: "007421" et pas juste "7421").
    code = f"{random.randint(0, 999999):06d}"

    user.code_verification = code
    user.code_verification_envoye_le = timezone.now()
    user.save()

    # Le compte est déjà créé/sauvegardé à ce stade : si l'envoi échoue
    # (SMTP Gmail lent ou bloqué, par ex. sur certains hébergeurs), on ne
    # doit pas faire planter la requête (500) alors que l'inscription a
    # réellement réussi côté base de données. L'utilisateur pourra toujours
    # redemander un code via /auth/resend-code.
    try:
        send_mail(
            subject="Votre code de vérification Sama-Terrain",
            message=(
                f"Bonjour {user.prenom},\n\n"
                f"Voici votre code de vérification : {code}\n\n"
                "Ce code est valable 15 minutes."
            ),
            from_email=None,  # utilise DEFAULT_FROM_EMAIL défini dans settings.py
            recipient_list=[user.email],
        )
    except Exception as erreur:
        # On affiche juste l'erreur dans les logs du serveur (visible sur
        # Render par exemple), sans bloquer l'inscription qui a déjà réussi.
        print(f"Erreur lors de l'envoi de l'email à {user.email} : {erreur}")


def generer_et_envoyer_code_reinitialisation(user):
    """
    Même mécanique que generer_et_envoyer_code (code à 6 chiffres, 15 min de
    validité, mêmes champs sur User), mais pour "mot de passe oublié" : le
    sujet/texte de l'email est différent pour ne pas semer la confusion avec
    un code de vérification de compte.
    """
    code = f"{random.randint(0, 999999):06d}"

    user.code_verification = code
    user.code_verification_envoye_le = timezone.now()
    user.save()

    try:
        send_mail(
            subject="Réinitialisation de votre mot de passe Sama-Terrain",
            message=(
                f"Bonjour {user.prenom},\n\n"
                f"Voici votre code de réinitialisation de mot de passe : {code}\n\n"
                "Ce code est valable 15 minutes. Si vous n'êtes pas à l'origine "
                "de cette demande, ignorez simplement cet email."
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as erreur:
        print(f"Erreur lors de l'envoi de l'email à {user.email} : {erreur}")
