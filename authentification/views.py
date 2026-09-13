from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer
from .utils import generer_et_envoyer_code


class RegisterView(APIView):
    """
    POST /api/auth/register

    Crée un compte "amateur" (role par défaut) et envoie un code de
    vérification à 6 chiffres par email. Le compte ne pourra pas se
    connecter tant que le code n'aura pas été validé (voir verify-email).
    """

    # N'importe qui peut appeler cette route, même sans être connecté.
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        # Si les données sont invalides (email déjà pris, mots de passe
        # différents, mot de passe trop faible...), on renvoie les erreurs.
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # `confirmPassword` ne fait pas partie du modèle User, on le retire
        # avant de créer l'utilisateur.
        donnees = serializer.validated_data
        donnees.pop('confirmPassword')
        mot_de_passe = donnees.pop('password')

        user = serializer.Meta.model(
            username=donnees['email'],  # on utilise l'email comme username interne
            **donnees,
        )
        user.set_password(mot_de_passe)  # hash le mot de passe, jamais en clair
        user.save()

        generer_et_envoyer_code(user)

        return Response(
            {
                'message': "Compte créé. Un code de vérification a été envoyé par email.",
                'email': user.email,
            },
            status=status.HTTP_201_CREATED,
        )
