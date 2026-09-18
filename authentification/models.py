from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import UserManager


class User(AbstractUser):
    """
    Notre utilisateur personnalisé.

    Par défaut, Django utilise un "username" pour se connecter.
    Ici, le frontend se connecte avec un EMAIL, donc on adapte le modèle.

    On garde quand même tous les champs de AbstractUser (first_name,
    last_name, password, is_active, ...) car on hérite de cette classe.
    On ajoute juste ce qu'il nous manque : le rôle et la vérification email.
    """

    # Les 3 rôles possibles sur la plateforme 
    class Role(models.TextChoices):
        AMATEUR = 'amateur', 'Amateur'
        GERANT = 'gerant', 'Gérant'
        ADMIN = 'admin', 'Admin'

    # On rend l'email unique et obligatoire : c'est lui qui sert d'identifiant de connexion
    email = models.EmailField(unique=True)

    # Le frontend utilise "prenom" et "nom" (et non first_name/last_name),
    # on ajoute donc ces deux champs pour coller exactement à ce qu'il envoie.
    prenom = models.CharField(max_length=150)
    nom = models.CharField(max_length=150)

    # Renseignés par l'utilisateur depuis sa page "Profil" (facultatifs).
    telephone = models.CharField(max_length=20, blank=True)
    ville_preferee = models.CharField(max_length=100, blank=True)

    # Le rôle de l'utilisateur. Par défaut, un nouvel inscrit est un "amateur".
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.AMATEUR,
    )

    # --- Vérification de l'email par code à 6 chiffres ---

    # Tant que ce champ est False, l'utilisateur ne peut pas se connecter.
    email_verifie = models.BooleanField(default=False)

    # Le code à 6 chiffres envoyé par email (ex: "482193"). Vide si déjà vérifié.
    code_verification = models.CharField(max_length=6, blank=True, null=True)

    # Date d'envoi du dernier code, pour savoir s'il a expiré.
    code_verification_envoye_le = models.DateTimeField(blank=True, null=True)

    # On dit à Django : "connecte-toi avec l'email", pas avec le username.
    USERNAME_FIELD = 'email'

    # Champs demandés en plus de USERNAME_FIELD et du mot de passe
    # quand on crée un superuser via `createsuperuser`.
    # NB : le champ "username" hérité de Django existe toujours en base,
    # mais on le remplit automatiquement avec l'email (voir views.py) :
    # l'utilisateur, lui, n'a jamais besoin de le connaître.
    REQUIRED_FIELDS = ['prenom', 'nom']

    # On indique à Django que c'est notre UserManager personnalisé qui gère ce modèle.
    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"
