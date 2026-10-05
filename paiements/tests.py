import hashlib
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from authentification.models import User
from creneaux.models import Creneau
from reservations.models import Reservation
from terrains.models import Terrain

from .models import Abonnement, Paiement, Retrait

AVANCE = 15000


def creer_utilisateur(email, **champs):
    return User.objects.create(email=email, username=email, prenom='Test', nom='Test', **champs)


class PortefeuilleGerantTests(TestCase):
    """
    Les avances arrivent sur le compte de la plateforme et créditent le
    portefeuille du gérant, qui les retire vers son Wave / Orange Money.
    """

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.joueur = creer_utilisateur('joueur@test.sn')
        self.admin = creer_utilisateur('admin@test.sn', role='admin')
        self.terrain = Terrain.objects.create(
            gerant=self.gerant, nom='Terrain', type='Foot à 5', ville='Dakar',
            capacite=10, surface='Synthétique', prix_heure=30000,
        )
        self.client_gerant = APIClient()
        self.client_gerant.force_authenticate(self.gerant)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(self.admin)

    def _reservation_payee(self, debut_dans):
        """Réservation confirmée dont l'avance a été payée, pour un match qui commence dans `debut_dans`."""
        debut = timezone.localtime() + debut_dans
        creneau = Creneau.objects.create(
            terrain=self.terrain, date=debut.date(), heure_debut=debut.time().replace(microsecond=0),
            heure_fin=(debut + timedelta(hours=1)).time().replace(microsecond=0), prix=30000,
            statut=Creneau.Statut.CONFIRME,
        )
        reservation = Reservation.objects.create(
            amateur=self.joueur, creneau=creneau, statut=Reservation.Statut.CONFIRMEE,
            nom_complet='Joueur', telephone='221771234567', montant_avance=AVANCE, montant_total=30000,
            moyen_paiement='wave', expire_le=timezone.now(),
        )
        Paiement.objects.create(type=Paiement.Type.AVANCE, reservation=reservation, montant=AVANCE)
        return reservation

    def _portefeuille(self):
        return self.client_gerant.get('/api/gerant/portefeuille/').data

    def _enregistrer_numero(self, numero='771234567'):
        return self.client_gerant.put('/api/gerant/portefeuille/', {'operateur': 'wave', 'numero': f'221{numero}'})

    def _retirer(self, montant):
        return self.client_gerant.post('/api/gerant/portefeuille/retraits/', {'montant': montant})

    def test_avance_debloquee_a_moins_de_24h_du_match(self):
        self._reservation_payee(timedelta(hours=2))
        self._reservation_payee(timedelta(days=3))
        etat = self._portefeuille()
        self.assertEqual(etat['solde_disponible'], AVANCE)
        # Le joueur peut encore annuler et être remboursé : pas encore retirable.
        self.assertEqual(etat['a_venir'], AVANCE)

    def test_avance_remboursee_ne_revient_pas_au_gerant(self):
        reservation = self._reservation_payee(timedelta(days=3))
        client_joueur = APIClient()
        client_joueur.force_authenticate(self.joueur)
        self.assertEqual(client_joueur.delete(f'/api/reservations/{reservation.id}/').status_code, 200)
        self.assertTrue(Paiement.objects.filter(type=Paiement.Type.REMBOURSEMENT).exists())
        self.assertEqual(self._portefeuille()['a_venir'], 0)

    @override_settings(FRAIS_TRANSACTION_POURCENT=2)
    def test_frais_de_transaction_deduits_du_remboursement(self):
        reservation = self._reservation_payee(timedelta(days=3))
        client_joueur = APIClient()
        client_joueur.force_authenticate(self.joueur)
        reponse = client_joueur.delete(f'/api/reservations/{reservation.id}/')
        self.assertEqual(reponse.data['frais_annulation'], 300)
        self.assertEqual(reponse.data['montant_rembourse'], AVANCE - 300)
        remboursement = Paiement.objects.get(type=Paiement.Type.REMBOURSEMENT)
        self.assertEqual(remboursement.montant, AVANCE - 300)

    def test_numero_invalide_refuse(self):
        self.assertEqual(self._enregistrer_numero('123').status_code, 400)

    def test_retrait_sans_numero_refuse(self):
        self._reservation_payee(timedelta(hours=-2))
        reponse = self._retirer(AVANCE)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('numéro', reponse.data['detail'])

    def test_retrait_superieur_au_solde_refuse(self):
        self._enregistrer_numero()
        self._reservation_payee(timedelta(hours=-2))
        self.assertEqual(self._retirer(AVANCE + 1).status_code, 400)
        self.assertFalse(Retrait.objects.exists())

    def test_retrait_verse_par_l_admin(self):
        self._enregistrer_numero()
        self._reservation_payee(timedelta(hours=-2))

        reponse = self._retirer(10000)
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['numero'], '221771234567')
        etat = self._portefeuille()
        self.assertEqual((etat['solde_disponible'], etat['en_cours_de_versement']), (AVANCE - 10000, 10000))
        # Un seul retrait en attente à la fois.
        self.assertEqual(self._retirer(1000).status_code, 400)

        retrait_id = reponse.data['id']
        en_attente = self.client_admin.get('/api/admin/retraits/?statut=en_attente').data
        self.assertEqual([r['id'] for r in en_attente], [retrait_id])
        self.assertEqual(self.client_admin.post(f'/api/admin/retraits/{retrait_id}/verse/', {}).status_code, 400)
        reponse = self.client_admin.post(
            f'/api/admin/retraits/{retrait_id}/verse/', {'reference_transaction': 'WAVE-123'},
        )
        self.assertEqual(reponse.status_code, 200)

        etat = self._portefeuille()
        self.assertEqual((etat['solde_disponible'], etat['total_verse']), (AVANCE - 10000, 10000))
        self.assertEqual(Retrait.objects.get().traite_par, self.admin)

    def test_retrait_echoue_rend_le_montant_au_solde(self):
        self._enregistrer_numero()
        self._reservation_payee(timedelta(hours=-2))
        retrait_id = self._retirer(AVANCE).data['id']
        self.assertEqual(self._portefeuille()['solde_disponible'], 0)

        reponse = self.client_admin.post(f'/api/admin/retraits/{retrait_id}/echec/', {'motif': 'Numéro inconnu'})
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self._portefeuille()['solde_disponible'], AVANCE)

    def test_retraits_reserves_a_l_admin(self):
        self.assertEqual(self.client_gerant.get('/api/admin/retraits/').status_code, 403)


def sha256(texte):
    return hashlib.sha256(texte.encode()).hexdigest()


@override_settings(PAYTECH_API_KEY='cle-plateforme', PAYTECH_API_SECRET='secret-plateforme')
class IpnPaytechTests(TestCase):
    """Les notifications IPN doivent être signées avec les clés PayTech de la plateforme."""

    def setUp(self):
        gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        joueur = creer_utilisateur('joueur@test.sn')
        terrain = Terrain.objects.create(
            gerant=gerant, nom='Terrain', type='Foot à 5', ville='Dakar',
            capacite=10, surface='Synthétique', prix_heure=30000,
        )
        demain = timezone.localdate() + timedelta(days=1)
        creneau = Creneau.objects.create(
            terrain=terrain, date=demain, heure_debut='20:00', heure_fin='21:00', prix=30000,
        )
        self.reservation = Reservation.objects.create(
            amateur=joueur, creneau=creneau, nom_complet='Joueur', telephone='221771234567',
            montant_avance=AVANCE, montant_total=30000, expire_le=timezone.now() + timedelta(minutes=15),
        )

    def _ipn(self, api_key, api_secret, type_event='sale_complete'):
        return APIClient().post('/api/paiements/ipn/', {
            'type_event': type_event, 'ref_command': f'RES-{self.reservation.id}-1',
            'payment_method': 'Wave', 'token': 'tok',
            'api_key_sha256': sha256(api_key), 'api_secret_sha256': sha256(api_secret),
        })

    def _statut(self):
        self.reservation.refresh_from_db()
        return self.reservation.statut

    def test_ipn_authentique_confirme_la_reservation(self):
        self.assertEqual(self._ipn('cle-plateforme', 'secret-plateforme').status_code, 200)
        self.assertEqual(self._statut(), Reservation.Statut.CONFIRMEE)

    def test_ipn_falsifiee_refusee(self):
        self.assertEqual(self._ipn('fausse-cle', 'faux-secret').status_code, 403)
        self.assertEqual(self._statut(), Reservation.Statut.EN_ATTENTE)

    def test_ipn_paiement_annule_ne_confirme_pas(self):
        reponse = self._ipn('cle-plateforme', 'secret-plateforme', type_event='sale_canceled')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self._statut(), Reservation.Statut.EN_ATTENTE)
