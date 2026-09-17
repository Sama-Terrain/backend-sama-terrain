from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from gerant.models import DemandeGerant
from paiements.models import Abonnement

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Représente un utilisateur dans les réponses de l'API (login, /me, ...).
    Ne contient jamais le mot de passe.
    """

    class Meta:
        model = User
        fields = [
            'id', 'email', 'prenom', 'nom', 'telephone', 'ville_preferee',
            'role', 'email_verifie', 'date_joined',
        ]


class UpdateProfilSerializer(serializers.ModelSerializer):
    """
    Utilisé pour PATCH /api/auth/me (page "Profil" de l'espace amateur).
    L'email et le rôle ne sont volontairement pas modifiables ici.
    """

    class Meta:
        model = User
        fields = ['prenom', 'nom', 'telephone', 'ville_preferee']


class RegisterSerializer(serializers.ModelSerializer):
    """
    Vérifie et transforme les données envoyées par le formulaire d'inscription
    (prenom, nom, email, password, confirmPassword) en un User.
    """

    # Le frontend envoie "confirmPassword", on doit la lire même si elle
    # n'existe pas sur le modèle User (write_only = jamais renvoyée dans une réponse).
    confirmPassword = serializers.CharField(write_only=True)

    # On force la vérification des règles de sécurité de Django sur le mot de passe
    # (longueur minimale, pas trop commun, etc.)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['prenom', 'nom', 'email', 'password', 'confirmPassword']

    def validate_email(self, value):
        """Refuse l'inscription si l'email est déjà utilisé."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value

    def validate(self, data):
        """Vérifie que les deux mots de passe saisis sont identiques."""
        if data['password'] != data['confirmPassword']:
            raise serializers.ValidationError({
                'confirmPassword': "Les mots de passe ne correspondent pas."
            })
        return data


class VerifyEmailSerializer(serializers.Serializer):
    """
    Vérifie le code à 6 chiffres reçu par email.

    Ce n'est PAS un ModelSerializer car on ne crée/modifie pas un User
    directement à partir des données : on doit d'abord aller chercher
    l'utilisateur par son email, puis comparer le code à la main.
    """

    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        # On cherche l'utilisateur correspondant à l'email envoyé.
        try:
            user = User.objects.get(email__iexact=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({'email': "Aucun compte avec cet email."})

        if user.email_verifie:
            raise serializers.ValidationError({'email': "Cet email est déjà vérifié."})

        if user.code_verification != data['code']:
            raise serializers.ValidationError({'code': "Code de vérification incorrect."})

        # Le code n'est valable que 15 minutes après son envoi.
        expire = user.code_verification_envoye_le + timedelta(minutes=15)
        if timezone.now() > expire:
            raise serializers.ValidationError({'code': "Ce code a expiré, demandez-en un nouveau."})

        # On transmet l'utilisateur trouvé à la vue, pour éviter de le
        # rechercher une deuxième fois.
        data['user'] = user
        return data


class ResendCodeSerializer(serializers.Serializer):
    """
    Vérifie qu'un renvoi de code est possible pour l'email donné.
    Ne vérifie PAS de code : elle sert juste à retrouver l'utilisateur
    avant de lui envoyer un nouveau code.
    """

    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email__iexact=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Aucun compte avec cet email.")

        if user.email_verifie:
            raise serializers.ValidationError("Cet email est déjà vérifié.")

        # On garde l'utilisateur sous la main pour la vue.
        self.user = user
        return value


class LoginSerializer(TokenObtainPairSerializer):
    """
    Connexion par email + mot de passe.

    On part du serializer fourni par SimpleJWT (qui sait déjà vérifier
    le mot de passe et créer les tokens), et on ajoute juste :
    - le refus de connexion si l'email n'est pas encore vérifié
    - le rôle et les infos utilisateur dans la réponse
    """

    def validate(self, attrs):
        # `super().validate()` vérifie l'email/mot de passe et prépare les
        # tokens. Si les identifiants sont mauvais, elle lève déjà une erreur.
        data = super().validate(attrs)

        if not self.user.email_verifie:
            raise serializers.ValidationError(
                "Votre email n'est pas encore vérifié. Vérifiez votre boîte mail."
            )

        # On ajoute le rôle et les infos utilisateur à côté des tokens,
        # pour que le frontend sache qui est connecté sans appel supplémentaire.
        data['role'] = self.user.role
        data['user'] = UserSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    """
    Vérifie qu'un refresh token a bien été fourni, pour pouvoir le
    mettre sur liste noire (blacklist) et empêcher sa réutilisation.
    """

    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            self.token = RefreshToken(value)
        except Exception:
            raise serializers.ValidationError("Refresh token invalide.")
        return value

    def save(self):
        # Une fois blacklisté, ce refresh token ne pourra plus jamais
        # être utilisé pour obtenir un nouvel access token.
        self.token.blacklist()


class GoogleAuthSerializer(serializers.Serializer):
    """
    Connexion OU inscription via Google (bouton "Sign in with Google").

    Le frontend envoie le "credential" fourni par Google (un jeton signé
    par Google qui prouve l'identité de l'utilisateur). On demande à
    Google de vérifier ce jeton, puis :
    - si un compte existe déjà avec cet email -> on connecte
    - sinon -> on crée le compte automatiquement (email déjà vérifié par Google)
    """

    credential = serializers.CharField()

    def validate_credential(self, value):
        try:
            # google-auth vérifie la signature du jeton et qu'il a bien été
            # émis pour NOTRE application (IDCLIENT dans le .env).
            payload = google_id_token.verify_oauth2_token(
                value,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            raise serializers.ValidationError("Jeton Google invalide.")

        return payload

    def save(self):
        payload = self.validated_data['credential']
        email = payload['email']

        user, cree = User.objects.get_or_create(
            email__iexact=email,
            defaults={
                'username': email,
                'email': email,
                'prenom': payload.get('given_name', ''),
                'nom': payload.get('family_name', ''),
                # Google a déjà vérifié cet email, pas besoin d'un code.
                'email_verifie': True,
            },
        )

        if cree:
            # Ce compte ne se connectera jamais avec un mot de passe classique.
            user.set_unusable_password()
            user.save()
        elif not user.email_verifie:
            # Compte déjà existant (inscrit classiquement) mais pas encore
            # vérifié : Google vient de prouver que cet email lui appartient
            # bel et bien, donc on peut le marquer vérifié directement.
            user.email_verifie = True
            user.save()

        # On génère les mêmes tokens JWT que pour une connexion classique.
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'role': user.role,
            'user': UserSerializer(user).data,
        }


class DevenirGerantSerializer(serializers.ModelSerializer):
    """
    POST /api/auth/devenir-gerant

    Crée un compte gérant + sa demande de validation. Le compte reste
    inactif (is_active=False) tant qu'un admin n'a pas validé la demande
    (voir app admin_panel). Reprend le même formulaire que le frontend
    "Devenir gérant" (DevenirGerant.jsx) : infos personnelles + business.
    """

    confirmPassword = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    # Champs du modèle DemandeGerant, saisis en même temps que le compte.
    nom_complexe = serializers.CharField(max_length=150)
    quartier = serializers.CharField(max_length=100)
    adresse = serializers.CharField(max_length=255)
    whatsapp = serializers.CharField(max_length=20)
    document = serializers.FileField()

    class Meta:
        model = User
        fields = [
            'prenom', 'nom', 'email', 'password', 'confirmPassword',
            'nom_complexe', 'quartier', 'adresse', 'whatsapp', 'document',
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value

    def validate(self, data):
        if data['password'] != data['confirmPassword']:
            raise serializers.ValidationError({
                'confirmPassword': "Les mots de passe ne correspondent pas."
            })
        return data

    def create(self, validated_data):
        # On sépare les champs du User de ceux de la DemandeGerant.
        champs_demande = {
            'nom_complexe': validated_data.pop('nom_complexe'),
            'quartier': validated_data.pop('quartier'),
            'adresse': validated_data.pop('adresse'),
            'whatsapp': validated_data.pop('whatsapp'),
            'document': validated_data.pop('document'),
        }
        validated_data.pop('confirmPassword')
        mot_de_passe = validated_data.pop('password')

        user = User(
            username=validated_data['email'],
            role=User.Role.GERANT,
            is_active=False,  # inactif tant que l'admin n'a pas validé
            **validated_data,
        )
        user.set_password(mot_de_passe)
        user.save()

        DemandeGerant.objects.create(user=user, **champs_demande)
        Abonnement.objects.create(gerant=user)  # statut par défaut : en_attente_validation

        return user
