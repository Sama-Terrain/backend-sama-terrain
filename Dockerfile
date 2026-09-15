# Image de base : Python léger (Debian "slim"), suffisant pour Django.
FROM python:3.12-slim

# Empêche Python de créer des fichiers .pyc et force l'affichage direct
# des logs (utile pour voir les erreurs avec `docker compose logs`).
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances système nécessaires pour compiler psycopg (driver PostgreSQL)
# et Pillow (traitement d'images pour les photos de terrains).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# On copie d'abord uniquement requirements.txt : Docker met cette étape en
# cache, donc `pip install` ne se relance pas à chaque changement de code,
# seulement quand les dépendances changent.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le reste du code du backend.
COPY . .

# Script qui attend la base de données, applique les migrations, puis démarre.
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
