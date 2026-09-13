from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import User


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
