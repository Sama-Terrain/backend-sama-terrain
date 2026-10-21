from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import User

NOUVEAU_MOT_DE_PASSE = 'TerrainMermoz2026!'


class MotDePasseOublieTests(TestCase):
    """Parcours "mot de passe oublié" : email -> code -> nouveau mot de passe -> connecté."""

    def setUp(self):
        self.user = User.objects.create(
            email='awa@test.sn', username='awa@test.sn', prenom='Awa', nom='Diop', email_verifie=True,
        )
        self.user.set_password('AncienMotDePasse2026!')
        self.user.save()
        self.client = APIClient()

    def _demander_code(self):
        self.client.post('/api/auth/mot-de-passe-oublie', {'email': 'awa@test.sn'})
        self.user.refresh_from_db()
        return self.user.code_verification

    def _verifier(self, code):
        return self.client.post('/api/auth/verifier-code-reinitialisation', {'email': 'awa@test.sn', 'code': code})

    def test_parcours_complet_puis_connexion_automatique(self):
        code = self._demander_code()
        self.assertEqual(self._verifier(code).status_code, 200)

        reponse = self.client.post('/api/auth/reinitialiser-mot-de-passe', {
            'email': 'awa@test.sn', 'code': code, 'nouveau_mot_de_passe': NOUVEAU_MOT_DE_PASSE,
        })
        self.assertEqual(reponse.status_code, 200)
        # Connecté directement : mêmes jetons qu'une connexion classique.
        self.assertIn('access', reponse.data)
        self.assertEqual(reponse.data['user']['email'], 'awa@test.sn')

        connexion = self.client.post('/api/auth/login', {'email': 'awa@test.sn', 'password': NOUVEAU_MOT_DE_PASSE})
        self.assertEqual(connexion.status_code, 200)

    def test_le_code_ne_sert_qu_une_fois(self):
        code = self._demander_code()
        donnees = {'email': 'awa@test.sn', 'code': code, 'nouveau_mot_de_passe': NOUVEAU_MOT_DE_PASSE}
        self.assertEqual(self.client.post('/api/auth/reinitialiser-mot-de-passe', donnees).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/reinitialiser-mot-de-passe', donnees).status_code, 400)

    def test_code_faux_indique_les_essais_restants(self):
        self._demander_code()
        reponse = self._verifier('000000' if self.user.code_verification != '000000' else '111111')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('Il vous reste 4 essais', reponse.data['code'][0])

    def test_code_invalide_apres_5_essais_faux(self):
        code = self._demander_code()
        faux = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self._verifier(faux)
        # Même le bon code ne marche plus : il faut en demander un nouveau.
        reponse = self._verifier(code)
        self.assertEqual(reponse.status_code, 400)

        nouveau_code = self._demander_code()
        self.assertEqual(self._verifier(nouveau_code).status_code, 200)

    def test_code_expire(self):
        code = self._demander_code()
        User.objects.filter(pk=self.user.pk).update(code_verification_envoye_le=timezone.now() - timedelta(minutes=16))
        reponse = self._verifier(code)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('expiré', reponse.data['code'][0])

    def test_compte_inactif_pas_connecte_automatiquement(self):
        # Ex: gérant en attente de validation par un administrateur.
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        code = self._demander_code()
        reponse = self.client.post('/api/auth/reinitialiser-mot-de-passe', {
            'email': 'awa@test.sn', 'code': code, 'nouveau_mot_de_passe': NOUVEAU_MOT_DE_PASSE,
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn('access', reponse.data)


class VerificationEmailTests(TestCase):
    """Vérification de l'email après l'inscription : code -> compte vérifié et connecté."""

    def setUp(self):
        self.client = APIClient()
        self.client.post('/api/auth/register', {
            'prenom': 'Moussa', 'nom': 'Ba', 'email': 'moussa@test.sn',
            'password': NOUVEAU_MOT_DE_PASSE, 'confirmPassword': NOUVEAU_MOT_DE_PASSE,
        })
        self.user = User.objects.get(email='moussa@test.sn')

    def _verifier(self, code):
        return self.client.post('/api/auth/verify-email', {'email': 'moussa@test.sn', 'code': code})

    def test_bon_code_verifie_et_connecte_directement(self):
        reponse = self._verifier(self.user.code_verification)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('access', reponse.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verifie)

    def test_code_invalide_apres_5_essais_faux(self):
        bon_code = self.user.code_verification
        faux = '000000' if bon_code != '000000' else '111111'
        premier = self._verifier(faux)
        self.assertIn('Il vous reste 4 essais', premier.data['code'][0])
        for _ in range(4):
            self._verifier(faux)
        self.assertEqual(self._verifier(bon_code).status_code, 400)

        # Un nouveau code remet le compteur à zéro.
        self.client.post('/api/auth/resend-code', {'email': 'moussa@test.sn'})
        self.user.refresh_from_db()
        self.assertEqual(self._verifier(self.user.code_verification).status_code, 200)

    def test_gerant_en_attente_verifie_mais_pas_connecte(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        reponse = self._verifier(self.user.code_verification)
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn('access', reponse.data)
