from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentification.models import User
from paiements.models import Abonnement
from terrains.models import Terrain

from .models import Creneau


class CreationCreneauTests(TestCase):
    """POST /api/creneaux/ : un doublon ou un créneau passé donne une erreur 400, jamais 500."""

    def setUp(self):
        self.gerant = User.objects.create(
            email='gerant@test.sn', username='gerant@test.sn', prenom='Test', nom='Test', role='gerant',
        )
        Abonnement.objects.create(
            gerant=self.gerant, statut=Abonnement.Statut.ACTIF,
            date_fin_abonnement=timezone.now() + timedelta(days=30),
        )
        self.terrain = Terrain.objects.create(
            gerant=self.gerant, nom='Terrain Test', type='Foot à 5', ville='Dakar',
            adresse='Rue 1', capacite=10, surface='Synthétique', prix_heure=20000,
        )
        self.client_gerant = APIClient()
        self.client_gerant.force_authenticate(self.gerant)

    def _creer(self, date, heure_debut='20:00', heure_fin='21:00'):
        return self.client_gerant.post('/api/creneaux/', {
            'terrain': self.terrain.id, 'date': date,
            'heure_debut': heure_debut, 'heure_fin': heure_fin, 'prix': 20000,
        })

    def test_doublon_refuse_sans_erreur_serveur(self):
        demain = timezone.localdate() + timedelta(days=1)
        self.assertEqual(self._creer(demain).status_code, 201)
        reponse = self._creer(demain)
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(Creneau.objects.filter(terrain=self.terrain).count(), 1)

    def test_creneau_passe_refuse(self):
        hier = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self._creer(hier).status_code, 400)
        self.assertFalse(Creneau.objects.exists())
