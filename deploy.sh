#!/bin/bash
# deploy.sh — Immocore auf dem Server aktualisieren
# Aufruf: bash deploy.sh

set -e
# Ins Verzeichnis des Skripts wechseln (= Projektordner, z. B. /home/patrik/immocore)
cd "$(dirname "$0")"

echo "=== [1/5] Neuesten Code holen ==="
git pull origin main

echo "=== [2/5] Docker-Images bauen ==="
docker compose -f docker-compose.prod.yml build --no-cache

echo "=== [3/5] Container neu starten ==="
docker compose -f docker-compose.prod.yml up -d

echo "=== [4/5] Datenbank-Migrationen ==="
docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --no-input

echo "=== [5/5] Static Files sammeln ==="
docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --no-input

echo ""
echo "✅ Deploy abgeschlossen!"
docker compose -f docker-compose.prod.yml ps
