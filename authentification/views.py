from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework.parsers import FormParser, MultiPartParser

from .models import User
from .serializers import (
    DevenirGerantSerializer,
    GoogleAuthSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResendCodeSerializer,
    UpdateProfilSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from .utils import generer_et_envoyer_code
from paiements.n8n import notifier_n8n


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


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login

    Reçoit {email, password}. Si c'est correct et que l'email est vérifié,
    renvoie {access, refresh, role, user}.
    """

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


class GoogleAuthView(APIView):
    """
    POST /api/auth/google

    Reçoit {credential} (le jeton fourni par le bouton Google). Connecte
    l'utilisateur s'il existe déjà, ou crée son compte automatiquement.
    Renvoie la même forme de réponse que /api/auth/login.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.save(), status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/auth/logout

    Reçoit {refresh}. Met ce refresh token sur liste noire : il ne pourra
    plus servir à générer de nouveaux access tokens. Il faut être connecté
    (access token valide) pour appeler cette route.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        return Response({'message': "Déconnexion réussie."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET   /api/auth/me : infos de l'utilisateur connecté, à partir du token JWT.
    PATCH /api/auth/me : modifie son propre profil (page "Profil").
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UpdateProfilSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(UserSerializer(request.user).data)


class DevenirGerantView(APIView):
    """
    POST /api/auth/devenir-gerant

    Crée un compte gérant en attente de validation admin (voir la page
    "Devenir gérant" du frontend). Le compte est inactif jusqu'à
    validation (voir app admin_panel).
    """

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]  # un fichier (document) est envoyé

    def post(self, request):
        serializer = DevenirGerantSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        generer_et_envoyer_code(user)

        emails_admin = list(
            User.objects.filter(role=User.Role.ADMIN).values_list('email', flat=True)
        )
        demande = user.demande_gerant
        notifier_n8n('nouvelle_demande_gerant', {
            'emails_admin': emails_admin,
            'nom_gerant': f"{user.prenom} {user.nom}",
            'email_gerant': user.email,
            'nom_complexe': demande.nom_complexe,
            'quartier': demande.quartier,
        })

        return Response(
            {
                'message': (
                    "Votre demande a été envoyée. Vérifiez votre email, puis "
                    "attendez la validation de votre compte par un administrateur."
                ),
                'email': user.email,
            },
            status=status.HTTP_201_CREATED,
        )
