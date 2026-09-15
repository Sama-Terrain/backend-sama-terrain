# Sama-Terrain — Backend (Django REST Framework)

API REST de **Sama-Terrain** ("Mon Terrain" en wolof), plateforme sénégalaise de réservation en temps réel de créneaux pour complexes de mini-foot. Ce dossier contient l'API principale (Django), qui orchestre l'authentification, les terrains, les réservations, les paiements et communique avec le micro-service IA séparé (dossier `../IA`).

Projet réalisé dans le cadre de la certification **DWWM + IA** — Simplon Sénégal (programme Fabrique 360).

## Sommaire

- [Stack technique](#stack-technique)
- [Architecture générale](#architecture-générale)
- [Les 3 rôles de la plateforme](#les-3-rôles-de-la-plateforme)
- [Organisation du code (apps Django)](#organisation-du-code-apps-django)
- [Installation et lancement](#installation-et-lancement)
- [Variables d'environnement](#variables-denvironnement)
- [Documentation de l'API](#documentation-de-lapi)
- [Logique métier importante](#logique-métier-importante)
- [Commandes utiles](#commandes-utiles)

## Stack technique

| Composant | Choix |
|---|---|
| Framework | Django 6.1 + Django REST Framework |
| Base de données | PostgreSQL 16 (via Docker) |
| Authentification | JWT (`djangorestframework-simplejwt`) + Google OAuth2 (`google-auth`) |
| Documentation API | `drf-spectacular` (OpenAPI / Swagger) |
| Paiements | PayTech (agrège Wave et Orange Money) |
| Notifications | N8n (workflows externes, webhooks) |
| IA | Micro-service FastAPI séparé (voir `../IA/README.md`) — pas de modèle entraîné en interne, uniquement des LLM externes via OpenRouter |
| Conteneurisation | Docker + Docker Compose |
| Serveur d'application | Gunicorn |

## Architecture générale

```
┌─────────────┐      HTTP/JSON      ┌──────────────────┐      HTTP/JSON      ┌─────────────────┐
│   Frontend   │ ───────────────────▶│  Backend Django   │ ───────────────────▶│  Service IA      │
│  (React/Vite)│◀─────────────────── │  (ce dossier)      │◀─────────────────── │  (FastAPI)       │
└─────────────┘                     └────────┬─────────┘                     └────────┬────────┘
                                              │                                        │
                                              ▼                                        ▼
                                     ┌─────────────────┐                    ┌───────────────────┐
                                     │   PostgreSQL     │◀───────────────── │  Lecture seule DB  │
                                     └─────────────────┘                    └───────────────────┘
                                              │
                                              ▼
                                   ┌───────────────────────┐
                                   │  N8n (notifications)   │
                                   │  PayTech (paiements)   │
                                   └───────────────────────┘
```

Le service IA (FastAPI) tourne dans son **propre conteneur**, lit la même base Postgres (en lecture pour les statistiques réelles) et ne stocke aucune donnée métier — il calcule à la volée (demande, prix recommandé, réponses du chatbot) puis écrit ses résultats directement sur le modèle `Creneau` (`niveau_demande`, `prix_recommande_ia`).

## Les 3 rôles de la plateforme

- **Amateur** : joueur qui recherche et réserve un terrain, paie une avance en ligne (Wave/Orange Money via PayTech), reçoit un ticket QR, laisse un avis après avoir joué.
- **Gérant** : propriétaire de terrain. Doit être validé par un admin après inscription, bénéficie de **7 jours d'essai gratuit**, puis paie un abonnement de **7 500 FCFA/mois** pour garder l'accès à son espace (dashboard, gestion des créneaux/tarifs, revenus). Accès automatiquement suspendu si l'abonnement expire sans renouvellement.
- **Administrateur** : supervise la plateforme, valide/rejette les demandes de gérant, modère les avis, consulte le détail complet de chaque gérant (terrains, revenus, abonnement, paiements).

## Organisation du code (apps Django)

Chaque app Django a une responsabilité claire et ses propres `models.py` / `views.py` / `serializers.py` / `urls.py` / `permissions.py` :

| App | Rôle |
|---|---|
| `authentification/` | Modèle `User` personnalisé (connexion par email, pas username), inscription, vérification par code à 6 chiffres, connexion Google, JWT (login/refresh/logout) |
| `terrains/` | CRUD des terrains (nom, ville, surface, équipements, photos, prix), catalogue public + gestion côté gérant |
| `creneaux/` | Créneaux horaires datés d'un terrain (date + heure précises), génération/mise à jour de prix, champs enrichis par l'IA (`niveau_demande`, `prix_recommande_ia`) |
| `reservations/` | Réservation d'un créneau par un amateur, calcul avance/solde, expiration automatique après 15 min sans paiement, règles d'annulation/remboursement (24h) |
| `paiements/` | Journal de tous les paiements (avance, solde, abonnement gérant), intégration PayTech, gestion du cycle de vie de l'`Abonnement` gérant |
| `tickets/` | Ticket QR généré à la confirmation d'une réservation, scanné par le gérant à l'entrée du terrain |
| `avis/` | Avis (note + commentaire) laissés par un amateur après avoir joué, un seul avis par réservation, modération possible |
| `gerant/` | Vues de l'espace gérant (dashboard, revenus, abonnement), demande "Devenir gérant" (`DemandeGerant`), proxy vers le service IA (`/api/ia/...`) |
| `admin_panel/` | Vues réservées à l'administrateur : statistiques globales, gestion des utilisateurs, validation des gérants, modération des avis, détail complet d'un gérant |
| `config/` | Configuration du projet Django (settings, routage racine `urls.py`) |

## Installation et lancement

### Avec Docker (recommandé)

Le backend est pensé pour tourner avec les 3 services orchestrés par `docker-compose.yml` : PostgreSQL, l'API Django, et le micro-service IA.

```bash
# Depuis backend/
cp .env.example .env          # puis renseigner les vraies valeurs (voir plus bas)
docker compose up -d --build
```

- L'API est alors disponible sur **http://localhost:8000**
- Les migrations et la collecte des fichiers statiques sont exécutées automatiquement au démarrage du conteneur (voir `docker-entrypoint.sh`)
- Le code est monté en volume : modifier un fichier `.py` recharge automatiquement le serveur (Gunicorn `--reload`), pas besoin de rebuild à chaque changement

```bash
# Voir les logs en direct
docker compose logs -f backend

# Ouvrir un shell Django (utile pour du debug/queries manuelles)
docker compose exec backend python manage.py shell

# Créer un compte administrateur
docker compose exec backend python manage.py createsuperuser

# Redémarrer un service après un changement de variable d'environnement
docker compose up -d --force-recreate backend
```

### Sans Docker (environnement local classique)

Nécessite une instance PostgreSQL déjà démarrée et accessible.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # adapter DATABASE_URL vers votre Postgres local

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Variables d'environnement

Toutes les variables attendues sont listées dans `.env.example`. Résumé de leur rôle :

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | Clé secrète Django (signatures, sessions) — à garder privée |
| `DEBUG` | `True` en développement uniquement |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL (`postgres://user:pass@host:port/db`) |
| `ALLOWED_HOSTS` | Domaines autorisés à servir l'application |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP pour l'envoi des codes de vérification par email |
| `IDCLIENT` / `IDCLIENTGOOGLESCRET` | Identifiant et secret client Google OAuth2 (bouton "Sign in with Google") |
| `PAYTECH_API_KEY` / `PAYTECH_API_SECRET` / `PAYTECH_BASE_URL` | Identifiants de l'agrégateur de paiement PayTech (Wave/Orange Money) |
| `N8N_WEBHOOK_URL` | URL du webhook N8n qui déclenche les notifications automatiques |
| `IA_SERVICE_URL` | URL du micro-service IA (FastAPI) — `http://ia:8001` dans Docker, `http://127.0.0.1:8001` en local |
| `FRONTEND_URL` / `BACKEND_URL` | Utilisées pour construire des liens absolus (emails, redirections PayTech) |

**Important** : `IDCLIENT` doit être **identique** au `VITE_GOOGLE_CLIENT_ID` du frontend (même client OAuth Google des deux côtés).

## Documentation de l'API

Une documentation interactive Swagger est générée automatiquement à partir du code (`drf-spectacular`) :

- **Swagger UI** : `http://localhost:8000/api/docs/`
- **Schéma OpenAPI brut** : `http://localhost:8000/api/schema/`

Aperçu des préfixes de routes principaux (voir `config/urls.py`) :

| Préfixe | Contenu |
|---|---|
| `/api/auth/` | Inscription, connexion, vérification email, Google, JWT refresh |
| `/api/terrains/` | Catalogue public + gestion des terrains par le gérant |
| `/api/creneaux/` | Création/modification/suppression de créneaux |
| `/api/reservations/` | Réservation, historique, annulation |
| `/api/paiements/` | Initiation PayTech, callback IPN, abonnement gérant |
| `/api/tickets/` | Validation d'un ticket QR par le gérant |
| `/api/avis/` | Avis publics par terrain, création, signalement |
| `/api/gerant/` | Dashboard, revenus, abonnement (espace gérant connecté) |
| `/api/ia/` | Proxy vers le micro-service IA (prédictions, chatbot) |
| `/api/admin/` | Statistiques globales, gestion utilisateurs, validation gérants |

## Logique métier importante

Quelques règles qui ne sont pas évidentes en lisant juste les modèles :

- **Un créneau du jour dont l'heure de début est déjà passée n'est jamais montré comme disponible**, et ne peut pas être réservé même via un appel direct à l'API (double vérification : liste des créneaux ET création de réservation).
- **Une réservation non payée expire automatiquement après 15 minutes** (`DELAI_EXPIRATION_MINUTES`), libérant le créneau.
- **Annulation remboursée uniquement si elle intervient plus de 24h avant le match** (`DELAI_REMBOURSEMENT_HEURES`).
- **L'abonnement gérant n'a pas de tâche planifiée qui le marque "expiré"** : le statut réel (`Abonnement.est_actif`) est recalculé à la volée à partir des dates (`date_fin_essai` / `date_fin_abonnement`), pour ne jamais dépendre d'un cron qui pourrait ne pas tourner.
- **Un gérant avec un abonnement expiré** ne peut plus créer/modifier de terrains ni de créneaux, ni accéder à son dashboard — mais peut toujours consulter/payer sa page d'abonnement, pour ne jamais rester bloqué hors de la plateforme.
- **L'IA ne stocke rien elle-même** : ses résultats (`niveau_demande`, `prix_recommande_ia`) sont écrits directement sur les lignes `Creneau` concernées par le micro-service FastAPI, calculés à partir de vraies statistiques de réservation (jamais de valeurs inventées).
- **Un admin ne peut ni se suspendre ni se supprimer lui-même**, et un compte admin ne peut pas être supprimé depuis la page de gestion des utilisateurs (garde-fous côté `admin_panel`).

## Commandes utiles

```bash
# Lancer les vérifications système Django (config, modèles...)
docker compose exec backend python manage.py check

# Créer une migration après modification d'un modèle
docker compose exec backend python manage.py makemigrations

# Appliquer les migrations
docker compose exec backend python manage.py migrate

# Accéder à la base Postgres directement
docker compose exec db psql -U sama_user -d sama_terrain
```
