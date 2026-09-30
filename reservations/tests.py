from datetime import timedelta, time

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentification.models import User
from creneaux.models import Creneau
from paiements.models import Abonnement
from reservations.models import Reservation
from terrains.models import Terrain

DEMAIN = timezone.localdate() + timedelta(days=1)
AVANCE = 15000  # > 10 000 FCFA (minimum) et < prix d'une portion (30 000 FCFA)


def creer_utilisateur(email, **champs):
    return User.objects.create(email=email, username=email, prenom='Test', nom='Test', **champs)


class PortionsTerrainTests(TestCase):
    """
    Terrains divisibles en portions (voir Creneau.creneaux_en_conflit) :
    - une portion réservée ne bloque pas les autres portions ;
    - le terrain complet a besoin de toutes ses portions libres ;
    - le terrain complet réservé bloque toutes les portions.
    """

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.joueur_1 = creer_utilisateur('joueur1@test.sn')
        self.joueur_2 = creer_utilisateur('joueur2@test.sn')

        # Terrain divisible en 3 portions, avec son créneau de 20h créé par
        # le gérant via l'API (les portions doivent se créer toutes seules).
        # Terrain complet : 60 000 FCFA/h, chaque portion : 30 000 FCFA/h.
        self.terrain = self._creer_terrain('Terrain Parcelles', nombre_portions=3, prix_portion=30000)
        client_gerant = APIClient()
        client_gerant.force_authenticate(self.gerant)
        reponse = client_gerant.post('/api/creneaux/', {
            'terrain': self.terrain.id, 'date': DEMAIN, 'heure_debut': '20:00',
            'heure_fin': '21:00', 'prix': 60000,
        })
        self.assertEqual(reponse.status_code, 201)

        self.complet = Creneau.objects.get(terrain=self.terrain, portion=0)
        self.portion_1 = Creneau.objects.get(terrain=self.terrain, portion=1)
        self.portion_2 = Creneau.objects.get(terrain=self.terrain, portion=2)

    def _creer_terrain(self, nom, nombre_portions=1, prix_portion=None):
        return Terrain.objects.create(
            gerant=self.gerant, nom=nom, type='Foot à 5', ville='Parcelles Assainies',
            adresse='Unité 15', capacite=10, surface='Synthétique', prix_heure=60000,
            nombre_portions=nombre_portions, prix_portion=prix_portion,
        )

    def _reserver(self, joueur, creneau):
        client = APIClient()
        client.force_authenticate(joueur)
        return client.post('/api/reservations/', {
            'creneau': creneau.id, 'nom_complet': 'Joueur Test',
            'telephone': '221771234567', 'montant_avance': AVANCE,
        })

    def test_portions_creees_automatiquement(self):
        portions = Creneau.objects.filter(terrain=self.terrain, portion__gt=0)
        self.assertEqual(portions.count(), 3)
        # Prix d'une portion = celui choisi par le gérant, pas une division.
        self.assertEqual(self.portion_1.prix, 30000)
        self.assertEqual(self.complet.prix, 60000)

    def test_terrain_simple_toujours_reservable(self):
        terrain_simple = self._creer_terrain('Terrain simple')
        creneau = Creneau.objects.create(
            terrain=terrain_simple, date=DEMAIN, heure_debut=time(20), heure_fin=time(21), prix=30000,
        )
        self.assertEqual(self._reserver(self.joueur_1, creneau).status_code, 201)
        # Aucun créneau de portion n'a été créé pour un terrain simple.
        self.assertEqual(Creneau.objects.filter(terrain=terrain_simple).count(), 1)

    def test_ancien_creneau_sans_portion_fonctionne_comme_avant(self):
        # Un créneau créé avant l'ajout des portions a portion = 0 par défaut.
        terrain_simple = self._creer_terrain('Ancien terrain')
        creneau = Creneau.objects.create(
            terrain=terrain_simple, date=DEMAIN, heure_debut=time(18), heure_fin=time(19), prix=30000,
        )
        self.assertEqual(creneau.portion, 0)
        self.assertEqual(creneau.libelle_portion, '')
        self.assertEqual(self._reserver(self.joueur_1, creneau).status_code, 201)
        self.assertEqual(self._reserver(self.joueur_2, creneau).status_code, 400)

    def test_une_portion_peut_etre_reservee(self):
        self.assertEqual(self._reserver(self.joueur_1, self.portion_1).status_code, 201)
        self.portion_1.refresh_from_db()
        self.assertEqual(self.portion_1.statut, Creneau.Statut.EN_ATTENTE)

    def test_une_portion_reservee_ne_bloque_pas_les_autres(self):
        self._reserver(self.joueur_1, self.portion_1)
        self.assertEqual(self._reserver(self.joueur_2, self.portion_2).status_code, 201)

    def test_terrain_complet_refuse_si_une_portion_est_reservee(self):
        self._reserver(self.joueur_1, self.portion_1)
        self.assertFalse(self.complet.est_reservable())
        self.assertEqual(self._reserver(self.joueur_2, self.complet).status_code, 400)

    def test_terrain_complet_reserve_bloque_toutes_les_portions(self):
        self.assertEqual(self._reserver(self.joueur_1, self.complet).status_code, 201)
        for portion in Creneau.objects.filter(terrain=self.terrain, portion__gt=0):
            self.assertFalse(portion.est_reservable())
            self.assertEqual(self._reserver(self.joueur_2, portion).status_code, 400)

    def test_deux_joueurs_ne_peuvent_pas_reserver_la_meme_portion(self):
        self.assertEqual(self._reserver(self.joueur_1, self.portion_1).status_code, 201)
        self.assertEqual(self._reserver(self.joueur_2, self.portion_1).status_code, 400)
        self.assertEqual(Reservation.objects.filter(creneau=self.portion_1).count(), 1)

    def test_portion_liberee_apres_annulation(self):
        reponse = self._reserver(self.joueur_1, self.portion_1)
        client = APIClient()
        client.force_authenticate(self.joueur_1)
        client.delete(f"/api/reservations/{reponse.data['id']}/")
        self.complet.refresh_from_db()
        self.assertTrue(self.complet.est_reservable())

    def test_commande_groupee_refuse_complet_et_portion_ensemble(self):
        client = APIClient()
        client.force_authenticate(self.joueur_1)
        reponse = client.post('/api/reservations/groupe/', {
            'creneaux': [self.complet.id, self.portion_1.id], 'nom_complet': 'Joueur Test',
            'telephone': '221771234567', 'montant_avance': AVANCE,
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(Reservation.objects.exists())

    def test_liste_des_creneaux_indique_la_disponibilite_reelle(self):
        self._reserver(self.joueur_1, self.portion_1)
        reponse = APIClient().get(f'/api/terrains/{self.terrain.id}/creneaux/', {'date': DEMAIN})
        disponibilites = {c['libelle_portion']: c['disponible'] for c in reponse.data}
        self.assertEqual(disponibilites, {
            'Terrain complet': False, 'Portion 1': False, 'Portion 2': True, 'Portion 3': True,
        })


class PrixPortionTests(TestCase):
    """Un terrain divisible doit avoir un prix de portion réservable."""

    def setUp(self):
        self.gerant = creer_utilisateur('gerant@test.sn', role='gerant')
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.gerant)

    def _creer(self, **champs):
        donnees = {
            'nom': 'Terrain', 'type': 'Foot à 5', 'ville': 'Dakar', 'adresse': 'x',
            'capacite': 10, 'surface': 'Synthétique', 'prix_heure': 60000, **champs,
        }
        return self.client.post('/api/terrains/', donnees)

    def test_terrain_divisible_sans_prix_de_portion_refuse(self):
        reponse = self._creer(nombre_portions=2)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('prix_portion', reponse.data)

    def test_prix_de_portion_trop_bas_refuse(self):
        # Avec 10 000 FCFA, aucune avance (> 10 000 et < prix) ne serait possible.
        self.assertEqual(self._creer(nombre_portions=2, prix_portion=10000).status_code, 400)

    def test_terrain_divisible_avec_prix_de_portion_accepte(self):
        self.assertEqual(self._creer(nombre_portions=2, prix_portion=30000).status_code, 201)

    def test_terrain_simple_sans_prix_de_portion_accepte(self):
        self.assertEqual(self._creer().status_code, 201)
