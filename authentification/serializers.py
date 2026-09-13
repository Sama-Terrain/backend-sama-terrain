from django.contrib.auth.password_validation import validate_password
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
