from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentification.models import User
from avis.models import Avis
from creneaux.models import Creneau
from paiements.models import Abonnement
from paiements.views import _confirmer_reservation
from reservations.models import Reservation
from terrains.models import Terrain

from .models import Notification
from .services import notifier


def creer_utilisateur(email, **champs):
    return User.objects.create(email=email, username=email, prenom='Test', nom='Test', **champs)


def client_pour(utilisateur):
    client = APIClient()
    client.force_authenticate(utilisateur)
    return client


class NotificationsEvenementsTests(TestCase):
    """Les évènements de la plateforme créent les bonnes notifications."""

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.admin = creer_utilisateur('admin@test.sn', role='admin')
        self.joueur = creer_utilisateur('joueur@test.sn')
        self.terrain = Terrain.objects.create(
            gerant=self.gerant, nom='Terrain', type='Foot à 5', ville='Dakar',
            capacite=10, surface='Synthétique', prix_heure=30000,
        )

    def _reservation_en_attente(self):
        debut = timezone.localtime() + timedelta(days=3)
        creneau = Creneau.objects.create(
            terrain=self.terrain, date=debut.date(), heure_debut=debut.time().replace(microsecond=0),
            heure_fin=(debut + timedelta(hours=1)).time().replace(microsecond=0), prix=30000,
            statut=Creneau.Statut.EN_ATTENTE,
        )
        return Reservation.objects.create(
            amateur=self.joueur, creneau=creneau, nom_complet='Moussa Ba', telephone='221771234567',
            montant_avance=15000, montant_total=30000, expire_le=timezone.now() + timedelta(minutes=15),
        )

    def test_reservation_payee_puis_annulee_notifie_le_gerant(self):
        reservation = self._reservation_en_attente()
        _confirmer_reservation(reservation, 'wave', 'TX-1')
        client_pour(self.joueur).delete(f'/api/reservations/{reservation.id}/')

        notifications = Notification.objects.filter(destinataire=self.gerant)
        self.assertEqual([n.type for n in notifications], ['annulation', 'reservation'])
        self.assertEqual(notifications[1].lien, f'/gerant/reservations?reservation={reservation.id}')
        # Rien pour l'admin : ce n'est pas son activité.
        self.assertFalse(Notification.objects.filter(destinataire=self.admin).exists())

    def test_avis_signale_notifie_les_admins_une_seule_fois(self):
        reservation = self._reservation_en_attente()
        avis = Avis.objects.create(reservation=reservation, terrain=self.terrain, amateur=self.joueur, note=2)
        client = client_pour(self.joueur)
        client.post(f'/api/avis/{avis.id}/signaler/')
        client.post(f'/api/avis/{avis.id}/signaler/')

        self.assertEqual(Notification.objects.filter(destinataire=self.admin, titre='Avis signalé').count(), 1)


class NotificationsApiTests(TestCase):
    """Liste, lecture et nettoyage des notifications."""

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        self.autre = creer_utilisateur('autre@test.sn', role='gerant')
        self.client_gerant = client_pour(self.gerant)

    def test_liste_seulement_mes_notifications_avec_compteur(self):
        notifier(self.gerant, Notification.Type.AVIS, 'A', 'message')
        notifier(self.gerant, Notification.Type.AVIS, 'B', 'message')
        notifier(self.autre, Notification.Type.AVIS, 'C', 'message')

        data = self.client_gerant.get('/api/notifications/').data
        self.assertEqual(data['non_lues'], 2)
        self.assertEqual([n['titre'] for n in data['notifications']], ['B', 'A'])

    def test_marquer_une_puis_toutes_comme_lues(self):
        premiere = notifier(self.gerant, Notification.Type.AVIS, 'A', 'message')
        notifier(self.gerant, Notification.Type.AVIS, 'B', 'message')
        autre = notifier(self.autre, Notification.Type.AVIS, 'C', 'message')

        self.assertEqual(self.client_gerant.post(f'/api/notifications/{premiere.id}/lue/').status_code, 200)
        self.assertEqual(self.client_gerant.get('/api/notifications/').data['non_lues'], 1)
        # Impossible de toucher à la notification de quelqu'un d'autre.
        self.assertEqual(self.client_gerant.post(f'/api/notifications/{autre.id}/lue/').status_code, 404)

        self.client_gerant.post('/api/notifications/tout-lire/')
        self.assertEqual(self.client_gerant.get('/api/notifications/').data['non_lues'], 0)
        autre.refresh_from_db()
        self.assertFalse(autre.lue)

    def _notification_agee(self, jours, lue):
        notification = notifier(self.gerant, Notification.Type.AVIS, f'{jours}j lue={lue}', 'message')
        Notification.objects.filter(pk=notification.pk).update(
            cree_le=timezone.now() - timedelta(days=jours), lue=lue,
        )

    def test_nettoyage_des_lues_de_plus_de_90_jours(self):
        self._notification_agee(100, lue=True)    # supprimée
        self._notification_agee(100, lue=False)   # gardée : jamais lue
        self._notification_agee(30, lue=True)     # gardée : trop récente

        sortie = StringIO()
        call_command('nettoyer_notifications', stdout=sortie)

        self.assertIn('1 notification(s) supprimée(s)', sortie.getvalue())
        self.assertEqual(
            sorted(Notification.objects.values_list('titre', flat=True)),
            ['100j lue=False', '30j lue=True'],
        )

    def test_la_liste_nettoie_aussi_au_passage(self):
        self._notification_agee(100, lue=True)
        self.client_gerant.get('/api/notifications/')
        self.assertFalse(Notification.objects.exists())
