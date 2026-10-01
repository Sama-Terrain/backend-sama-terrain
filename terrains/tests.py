from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentification.models import User
from paiements.models import Abonnement
from terrains.models import Terrain


class PositionGpsTerrainTests(TestCase):
    """Position GPS obligatoire d'un terrain (latitude + longitude)."""

    def setUp(self):
        self.gerant = User.objects.create(
            email='gerant@test.sn', username='gerant@test.sn', prenom='G', nom='T', role='gerant',
        )
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.gerant)

    def _creer(self, **champs):
        # Même format que le formulaire du frontend (multipart/form-data).
        donnees = {
            'nom': 'Terrain', 'type': 'Foot à 5', 'ville': 'Parcelles Assainies',
            'capacite': 10, 'surface': 'Synthétique', 'prix_heure': 30000, **champs,
        }
        return self.client.post('/api/terrains/', donnees, format='multipart')

    def test_terrain_avec_position_gps(self):
        reponse = self._creer(latitude='14.764500', longitude='-17.439800')
        self.assertEqual(reponse.status_code, 201)
        terrain = Terrain.objects.get()
        self.assertEqual(terrain.latitude, Decimal('14.764500'))
        self.assertEqual(terrain.longitude, Decimal('-17.439800'))

    def test_terrain_sans_position_gps_refuse(self):
        # Champs vides envoyés par le formulaire : le message s'affiche sous la carte.
        reponse = self._creer(latitude='', longitude='')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('latitude', reponse.data)
        self.assertFalse(Terrain.objects.exists())

    def test_terrain_sans_adresse_accepte(self):
        # L'adresse écrite n'est plus demandée : la position GPS suffit.
        self.assertEqual(self._creer(latitude='14.764500', longitude='-17.439800').status_code, 201)
        self.assertEqual(Terrain.objects.get().adresse, '')

    def test_latitude_sans_longitude_refusee(self):
        self.assertEqual(self._creer(latitude='14.7645', longitude='').status_code, 400)

    def test_coordonnees_impossibles_refusees(self):
        self.assertEqual(self._creer(latitude='95', longitude='-17.43').status_code, 400)

    def test_position_visible_sur_la_fiche_publique(self):
        self._creer(latitude='14.764500', longitude='-17.439800')
        terrain = Terrain.objects.get()
        reponse = APIClient().get(f'/api/terrains/{terrain.id}/')
        self.assertEqual((reponse.data['latitude'], reponse.data['longitude']), ('14.764500', '-17.439800'))
