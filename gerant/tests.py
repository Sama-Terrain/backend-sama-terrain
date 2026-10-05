from datetime import time, timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentification.models import User
from creneaux.models import Creneau
from notifications.models import Notification
from paiements.models import Abonnement, Paiement
from paiements.views import _confirmer_reservation
from reservations.models import Reservation
from terrains.models import Terrain

from .models import Employe, JournalAction


def creer_utilisateur(email, **champs):
    return User.objects.create(email=email, username=email, prenom='Test', nom=email.split('@')[0], **champs)


def client_pour(utilisateur):
    client = APIClient()
    client.force_authenticate(utilisateur)
    return client


class EquipeGerantTests(TestCase):
    """Un gérant (propriétaire) et ses employés : accès partagé, droits limités, traçabilité."""

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.employe = creer_utilisateur('moussa@test.sn', role='employe')
        Employe.objects.create(user=self.employe, proprietaire=self.gerant)
        self.joueur = creer_utilisateur('joueur@test.sn')
        self.terrain = Terrain.objects.create(
            gerant=self.gerant, nom='Terrain Mermoz', type='Foot à 5', ville='Dakar',
            capacite=10, surface='Synthétique', prix_heure=30000,
        )
        self.client_gerant = client_pour(self.gerant)
        self.client_employe = client_pour(self.employe)

    def _reservation_payee_aujourdhui(self):
        creneau = Creneau.objects.create(
            terrain=self.terrain, date=timezone.localdate(), heure_debut=time(20, 0), heure_fin=time(21, 0),
            prix=30000, statut=Creneau.Statut.EN_ATTENTE,
        )
        reservation = Reservation.objects.create(
            amateur=self.joueur, creneau=creneau, nom_complet='Awa Diop', telephone='221771234567',
            montant_avance=15000, montant_total=30000, expire_le=timezone.now() + timedelta(minutes=15),
        )
        _confirmer_reservation(reservation, 'wave', 'TX-1')
        return reservation

    # --- Accès partagé et droits limités

    def test_employe_voit_les_reservations_de_son_employeur(self):
        reservation = self._reservation_payee_aujourdhui()
        reponse = self.client_employe.get('/api/gerant/reservations/')
        self.assertEqual([r['id'] for r in reponse.data], [reservation.id])
        self.assertEqual(self.client_employe.get(f'/api/reservations/{reservation.id}/').status_code, 200)
        self.assertEqual(self.client_employe.get('/api/terrains/?mine=true').status_code, 200)

    def test_employe_n_accede_ni_a_l_argent_ni_a_l_abonnement(self):
        for url in ['/api/gerant/dashboard/', '/api/gerant/revenus/', '/api/gerant/portefeuille/',
                    '/api/gerant/employes/', '/api/gerant/journal/']:
            self.assertEqual(self.client_employe.get(url).status_code, 403, url)
        self.assertEqual(self.client_employe.post('/api/paiements/abonnement/initier/').status_code, 403)
        # Il peut seulement CONSULTER l'abonnement de son employeur (accès ouvert ou non).
        self.assertEqual(self.client_employe.get('/api/gerant/abonnement/').data['statut'], 'actif')

    def test_employe_ne_cree_ni_ne_modifie_de_terrain(self):
        self.assertEqual(self.client_employe.post('/api/terrains/', {'nom': 'X'}).status_code, 403)
        self.assertEqual(self.client_employe.patch(f'/api/terrains/{self.terrain.id}/', {'nom': 'X'}).status_code, 403)

    def test_employe_bloque_si_abonnement_du_proprietaire_expire(self):
        Abonnement.objects.filter(gerant=self.gerant).update(date_fin_abonnement=timezone.now() - timedelta(days=1))
        reponse = self.client_employe.post('/api/creneaux/', {
            'terrain': self.terrain.id, 'date': timezone.localdate() + timedelta(days=1),
            'heure_debut': '20:00', 'heure_fin': '21:00', 'prix': 30000,
        })
        self.assertEqual(reponse.status_code, 403)

    def test_employe_d_un_autre_gerant_ne_peut_pas_valider_le_ticket(self):
        reservation = self._reservation_payee_aujourdhui()
        autre_gerant = creer_utilisateur('autre@test.sn', role='gerant')
        intrus = creer_utilisateur('intrus@test.sn', role='employe')
        Employe.objects.create(user=intrus, proprietaire=autre_gerant)

        reponse = client_pour(intrus).post('/api/tickets/valider/', {'code': str(reservation.ticket.code)})
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(client_pour(intrus).get('/api/gerant/reservations/').data, [])

    # --- Traçabilité : qui a fait quoi

    def test_scan_et_encaissement_traces_au_nom_de_l_employe(self):
        reservation = self._reservation_payee_aujourdhui()
        self.assertEqual(self.client_employe.post('/api/tickets/valider/', {'code': str(reservation.ticket.code)}).status_code, 200)
        self.assertEqual(self.client_employe.post('/api/paiements/solde/', {'reservation': reservation.id, 'moyen_paiement': 'cash'}).status_code, 201)

        reservation.ticket.refresh_from_db()
        self.assertEqual(reservation.ticket.valide_par, self.employe)
        self.assertEqual(Paiement.objects.get(type=Paiement.Type.SOLDE).encaisse_par, self.employe)

        journal = self.client_gerant.get('/api/gerant/journal/').data
        self.assertEqual([j['action'] for j in journal], ['solde_encaisse', 'ticket_valide'])
        self.assertTrue(all(j['auteur_id'] == self.employe.id for j in journal))

        detail = self.client_gerant.get(f'/api/reservations/{reservation.id}/').data
        self.assertEqual(detail['ticket']['valide_par'], 'Test moussa')
        self.assertEqual(detail['solde_encaisse']['encaisse_par'], 'Test moussa')

    def test_creations_de_creneaux_regroupees_dans_le_journal(self):
        demain = timezone.localdate() + timedelta(days=1)
        for heure in ['18:00', '19:00', '20:00']:
            self.client_employe.post('/api/creneaux/', {
                'terrain': self.terrain.id, 'date': demain, 'heure_debut': heure,
                'heure_fin': f"{int(heure[:2]) + 1}:00", 'prix': 30000,
            })

        lignes = JournalAction.objects.filter(proprietaire=self.gerant)
        self.assertEqual(lignes.count(), 1)
        self.assertEqual(lignes[0].nombre, 3)
        self.assertEqual(lignes[0].description, '3 créneaux créés sur Terrain Mermoz')

    def test_journal_filtrable_par_auteur(self):
        journal_vide = self.client_gerant.get(f'/api/gerant/journal/?auteur={self.employe.id}').data
        self.assertEqual(journal_vide, [])

    def test_nouvelle_reservation_notifie_gerant_et_employes(self):
        self._reservation_payee_aujourdhui()
        destinataires = set(Notification.objects.filter(type='reservation').values_list('destinataire', flat=True))
        self.assertEqual(destinataires, {self.gerant.id, self.employe.id})

    # --- Gestion de l'équipe par le propriétaire

    def test_ajout_d_un_employe_envoie_une_invitation(self):
        reponse = self.client_gerant.post('/api/gerant/employes/', {
            'prenom': 'Fatou', 'nom': 'Sall', 'email': 'Fatou@Test.sn', 'telephone': '221771112233',
        })
        self.assertEqual(reponse.status_code, 201)
        self.assertFalse(reponse.data['invitation_acceptee'])

        fatou = User.objects.get(email='fatou@test.sn')
        self.assertEqual(fatou.role, 'employe')
        self.assertFalse(fatou.has_usable_password())
        self.assertEqual(fatou.profil_employe.proprietaire, self.gerant)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/mot-de-passe-oublie?email=fatou%40test.sn', mail.outbox[0].body)
        self.assertTrue(JournalAction.objects.filter(action='employe_ajoute').exists())

        # Un email déjà utilisé est refusé.
        doublon = self.client_gerant.post('/api/gerant/employes/', {'prenom': 'A', 'nom': 'B', 'email': 'moussa@test.sn'})
        self.assertEqual(doublon.status_code, 400)

    def test_parcours_complet_invitation_mot_de_passe_connexion(self):
        self.client_gerant.post('/api/gerant/employes/', {'prenom': 'Fatou', 'nom': 'Sall', 'email': 'fatou@test.sn'})
        anonyme = APIClient()
        # Sans mot de passe choisi, impossible de se connecter.
        self.assertEqual(anonyme.post('/api/auth/login', {'email': 'fatou@test.sn', 'password': 'x'}).status_code, 401)

        # L'employée suit le lien de l'invitation : elle reçoit un code et choisit son mot de passe.
        anonyme.post('/api/auth/mot-de-passe-oublie', {'email': 'fatou@test.sn'})
        code = User.objects.get(email='fatou@test.sn').code_verification
        anonyme.post('/api/auth/reinitialiser-mot-de-passe', {
            'email': 'fatou@test.sn', 'code': code, 'nouveau_mot_de_passe': 'TerrainMermoz2026!',
        })

        connexion = anonyme.post('/api/auth/login', {'email': 'fatou@test.sn', 'password': 'TerrainMermoz2026!'})
        self.assertEqual(connexion.status_code, 200)
        self.assertEqual(connexion.data['role'], 'employe')
        self.assertEqual(connexion.data['user']['equipe']['proprietaire_id'], self.gerant.id)
        employes = self.client_gerant.get('/api/gerant/employes/').data
        self.assertTrue(next(e for e in employes if e['email'] == 'fatou@test.sn')['invitation_acceptee'])

    def test_employe_desactive_ne_peut_plus_se_connecter(self):
        client_jwt = APIClient()
        client_jwt.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.employe).access_token}')
        self.assertEqual(client_jwt.get('/api/gerant/reservations/').status_code, 200)

        reponse = self.client_gerant.patch(f'/api/gerant/employes/{self.employe.id}/', {'actif': False}, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.data['actif'])
        # Même avec une session déjà ouverte, l'accès est coupé immédiatement.
        self.assertEqual(client_jwt.get('/api/gerant/reservations/').status_code, 401)

    def test_un_gerant_ne_gere_pas_les_employes_des_autres(self):
        autre_gerant = creer_utilisateur('autre@test.sn', role='gerant')
        reponse = client_pour(autre_gerant).patch(f'/api/gerant/employes/{self.employe.id}/', {'actif': False}, format='json')
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(client_pour(autre_gerant).get('/api/gerant/employes/').data, [])
