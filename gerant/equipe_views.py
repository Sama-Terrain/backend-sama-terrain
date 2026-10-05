from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentification.models import User

from .equipe import journaliser
from .models import Employe, JournalAction
from .permissions import EstGerant
from .serializers import AjouterEmployeSerializer, EmployeSerializer, JournalActionSerializer

# Nombre de lignes du journal renvoyées (les plus récentes).
JOURNAL_MAX = 200


def envoyer_invitation(employe):
    """
    Email d'invitation : l'employé choisit lui-même son mot de passe via le
    parcours "mot de passe oublié" (code à 6 chiffres). Le gérant ne connaît
    donc jamais le mot de passe de ses employés, et chaque action du journal
    est bien celle de la personne indiquée.
    """
    user, gerant = employe.user, employe.proprietaire
    lien = f"{settings.FRONTEND_URL}/mot-de-passe-oublie?email={quote(user.email)}"
    try:
        send_mail(
            subject="Votre accès employé Sama-Terrain",
            message=(
                f"Bonjour {user.prenom},\n\n"
                f"{gerant.prenom} {gerant.nom} vous a ajouté(e) comme employé(e) sur Sama-Terrain "
                "pour gérer ses terrains au quotidien (réservations, scan des tickets, créneaux).\n\n"
                "Pour activer votre compte, choisissez votre mot de passe :\n"
                f"1. Ouvrez ce lien : {lien}\n"
                "2. Cliquez sur « Envoyer le code » : un code à 6 chiffres vous est envoyé par email.\n"
                "3. Saisissez ce code et votre nouveau mot de passe (le code est valable 15 minutes).\n\n"
                "Vous pourrez ensuite vous connecter avec votre adresse email."
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as erreur:
        # Même logique que les autres emails : l'employé est créé, l'envoi
        # pourra être relancé depuis la page "Mon équipe".
        print(f"Erreur lors de l'envoi de l'invitation à {user.email} : {erreur}")


class EmployesView(APIView):
    """
    GET  /api/gerant/employes/ -> les employés du gérant connecté
    POST /api/gerant/employes/ -> ajoute un employé et lui envoie son invitation

    Réservé au gérant propriétaire (un employé ne gère pas l'équipe).
    """

    permission_classes = [EstGerant]

    def get(self, request):
        employes = Employe.objects.filter(proprietaire=request.user).select_related('user').order_by('-ajoute_le')
        return Response(EmployeSerializer(employes, many=True).data)

    def post(self, request):
        serializer = AjouterEmployeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        donnees = serializer.validated_data
        user = User(
            username=donnees['email'], email=donnees['email'],
            prenom=donnees['prenom'], nom=donnees['nom'], telephone=donnees.get('telephone', ''),
            role=User.Role.EMPLOYE,
            # L'email sera prouvé par le code reçu pour choisir le mot de passe.
            email_verifie=True,
        )
        user.set_unusable_password()
        user.save()
        employe = Employe.objects.create(user=user, proprietaire=request.user)

        envoyer_invitation(employe)
        journaliser(
            request.user, JournalAction.Action.EMPLOYE_AJOUTE,
            f"{user.prenom} {user.nom} ajouté(e) à l'équipe",
        )
        return Response(EmployeSerializer(employe).data, status=status.HTTP_201_CREATED)


class EmployeDetailView(APIView):
    """
    PATCH /api/gerant/employes/:id/ {"actif": false} -> désactive (ou réactive) un employé.

    On ne supprime jamais un employé : son compte est désactivé (il ne peut
    plus se connecter, même avec une session ouverte) et le journal garde
    la trace de ce qu'il a fait.
    """

    permission_classes = [EstGerant]

    def patch(self, request, pk):
        employe = Employe.objects.filter(user_id=pk, proprietaire=request.user).select_related('user').first()
        if employe is None:
            return Response({'detail': "Employé introuvable."}, status=status.HTTP_404_NOT_FOUND)

        actif = request.data.get('actif')
        if not isinstance(actif, bool):
            return Response({'actif': ["Valeur attendue : true ou false."]}, status=status.HTTP_400_BAD_REQUEST)

        if employe.user.is_active != actif:
            employe.user.is_active = actif
            employe.user.save(update_fields=['is_active'])
            journaliser(
                request.user,
                JournalAction.Action.EMPLOYE_REACTIVE if actif else JournalAction.Action.EMPLOYE_DESACTIVE,
                f"{employe.user.prenom} {employe.user.nom} {'réactivé(e)' if actif else 'désactivé(e)'}",
            )
        return Response(EmployeSerializer(employe).data)


class RenvoyerInvitationView(APIView):
    """POST /api/gerant/employes/:id/invitation/ -> renvoie l'email d'invitation."""

    permission_classes = [EstGerant]

    def post(self, request, pk):
        employe = Employe.objects.filter(user_id=pk, proprietaire=request.user).select_related('user').first()
        if employe is None:
            return Response({'detail': "Employé introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if employe.user.has_usable_password():
            return Response({'detail': "Cet employé a déjà activé son compte."}, status=status.HTTP_400_BAD_REQUEST)
        envoyer_invitation(employe)
        return Response({'message': "Invitation renvoyée."})


class JournalEquipeView(APIView):
    """
    GET /api/gerant/journal/?auteur=<id>&action=<action>

    Journal d'activité de l'équipe (le gérant et ses employés) : qui a
    validé un ticket, encaissé un solde, modifié des créneaux... Réservé
    au gérant propriétaire.
    """

    permission_classes = [EstGerant]

    def get(self, request):
        journal = JournalAction.objects.filter(proprietaire=request.user)

        auteur = request.query_params.get('auteur')
        if auteur:
            journal = journal.filter(auteur_id=auteur)
        action = request.query_params.get('action')
        if action:
            journal = journal.filter(action=action)

        return Response(JournalActionSerializer(journal[:JOURNAL_MAX], many=True).data)
