from rest_framework import serializers

from authentification.models import User
from authentification.serializers import UpdateProfilSerializer

from .models import Employe, JournalAction


class AjouterEmployeSerializer(UpdateProfilSerializer):
    """
    POST /api/gerant/employes/ : le gérant ajoute un employé.
    Mêmes règles que le profil (prénom/nom obligatoires, téléphone sénégalais
    facultatif), plus un email qui ne doit pas déjà avoir de compte.
    Pas de mot de passe : l'employé le choisit lui-même (voir invitation).
    """

    email = serializers.EmailField()

    class Meta(UpdateProfilSerializer.Meta):
        fields = ['prenom', 'nom', 'email', 'telephone']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value.lower()


class EmployeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    prenom = serializers.CharField(source='user.prenom', read_only=True)
    nom = serializers.CharField(source='user.nom', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    telephone = serializers.CharField(source='user.telephone', read_only=True)
    actif = serializers.BooleanField(source='user.is_active', read_only=True)
    derniere_connexion = serializers.DateTimeField(source='user.last_login', read_only=True)
    # False tant que l'employé n'a pas encore choisi son mot de passe.
    invitation_acceptee = serializers.SerializerMethodField()

    class Meta:
        model = Employe
        fields = [
            'id', 'prenom', 'nom', 'email', 'telephone', 'actif',
            'ajoute_le', 'derniere_connexion', 'invitation_acceptee',
        ]

    def get_invitation_acceptee(self, employe):
        return employe.user.has_usable_password()


class JournalActionSerializer(serializers.ModelSerializer):
    action_libelle = serializers.CharField(source='get_action_display', read_only=True)
    auteur_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = JournalAction
        fields = [
            'id', 'auteur_id', 'auteur_nom', 'action', 'action_libelle',
            'description', 'nombre', 'cree_le', 'mis_a_jour_le',
        ]
