from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer, ResendCodeSerializer, VerifyEmailSerializer
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


class VerifyEmailView(APIView):
    """
    POST /api/auth/verify-email

    Reçoit {email, code}. Si le code est bon et pas expiré, on marque
    le compte comme vérifié : l'utilisateur peut désormais se connecter.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']

        # Le compte est vérifié : on active email_verifie et on efface le
        # code pour qu'il ne puisse plus être réutilisé.
        user.email_verifie = True
        user.code_verification = None
        user.code_verification_envoye_le = None
        user.save()

        return Response({'message': "Email vérifié avec succès."}, status=status.HTTP_200_OK)


class ResendCodeView(APIView):
    """
    POST /api/auth/resend-code

    Reçoit {email}. Génère un nouveau code de vérification et le renvoie
    par email (remplace l'ancien code, même s'il n'avait pas expiré).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # validate_email() a mis l'utilisateur trouvé sur le serializer.
        generer_et_envoyer_code(serializer.user)

        return Response(
            {'message': "Un nouveau code de vérification a été envoyé."},
            status=status.HTTP_200_OK,
        )
