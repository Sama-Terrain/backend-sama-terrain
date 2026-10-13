import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User


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
    user.tentatives_code = 0
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
            recipient_list=[user.email], # liste des destinataires (ici, juste l'email de l'utilisateur)
        )
    except Exception as erreur:
        # On affiche juste l'erreur dans les logs du serveur (visible sur
        # Render par exemple), sans bloquer l'inscription qui a déjà réussi.
        print(f"Erreur lors de l'envoi de l'email à {user.email} : {erreur}")


# Un code (vérification d'email ou réinitialisation) est valable 15 minutes
# et accepte au plus 5 essais faux.
DUREE_VALIDITE_CODE = timedelta(minutes=15)
TENTATIVES_CODE_MAX = 5


def verifier_code(user, code):
    """
    Vérifie le code à 6 chiffres saisi par `user`. Renvoie None s'il est bon,
    sinon le message d'erreur à afficher. Chaque code faux est compté : au
    5e essai raté, le code est effacé et il faut en demander un nouveau.
    """
    if not user.code_verification:
        return "Aucun code en cours : demandez un nouveau code."

    if timezone.now() > user.code_verification_envoye_le + DUREE_VALIDITE_CODE:
        return "Ce code a expiré, demandez-en un nouveau."

    if user.code_verification != code:
        user.tentatives_code += 1
        restantes = TENTATIVES_CODE_MAX - user.tentatives_code
        if restantes <= 0:
            user.code_verification = None
            user.code_verification_envoye_le = None
            user.save(update_fields=['tentatives_code', 'code_verification', 'code_verification_envoye_le'])
            return "Trop de codes incorrects : ce code n'est plus valable, demandez-en un nouveau."
        user.save(update_fields=['tentatives_code'])
        return f"Code incorrect. Il vous reste {restantes} essai{'s' if restantes > 1 else ''}."

    return None


def generer_et_envoyer_code_reinitialisation(user):
    """
    Même mécanique que generer_et_envoyer_code (code à 6 chiffres, 15 min de
    validité, mêmes champs sur User), mais pour "mot de passe oublié" : le
    sujet/texte de l'email est différent pour ne pas semer la confusion avec
    un code de vérification de compte.
    """
    # Un nombre aléatoire à 6 chiffres, toujours écrit sur 6 caractères
    # randint(0, 999999) génère un entier aléatoire entre 0 et 999999 inclus. Le formatage f"{...:06d}" 
    # permet de s'assurer que le nombre est représenté sur 6 chiffres, en ajoutant des zéros à gauche si nécessaire (ex: "007421" au lieu de "7421").
    code = f"{random.randint(0, 999999):06d}"

    user.code_verification = code
    user.code_verification_envoye_le = timezone.now()
    user.tentatives_code = 0
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


# --- Activation du compte d'un employé (invitation envoyée par son gérant) ---
#
# Lien sécurisé à usage unique, sans code à recopier : le jeton est signé par
# Django (même mécanique que la réinitialisation de mot de passe de Django) et
# devient invalide dès que l'employé a choisi son mot de passe. Il expire
# après PASSWORD_RESET_TIMEOUT (3 jours par défaut).

def lien_activation_employe(user):
    """URL du frontend où l'employé choisit son mot de passe."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/activer-compte?uid={uid}&token={token}"


def employe_depuis_lien(uid, token):
    """
    L'employé correspondant à un lien d'activation, ou None si le lien est
    invalide, expiré, déjà utilisé ou si le compte a été désactivé.
    """
    if not uid or not token:
        return None
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None

    if user.role != User.Role.EMPLOYE or not user.is_active:
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user
