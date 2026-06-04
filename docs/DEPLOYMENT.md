# IMMOCORE — Deployment auf Strato VPS

## Verbindung

```bash
ssh -i $env:USERPROFILE\.ssh\strato_server_key patrik@87.106.219.148
```

## Standard-Deployment (Code + Frontend + Migrationen)

```bash
# 1. Merge in main + Push (lokal)
git checkout main
git merge feature/BRANCHNAME --no-ff
git push origin main

# 2. Auf dem Server
ssh -i "$USERPROFILE/.ssh/strato_server_key" -o StrictHostKeyChecking=no patrik@87.106.219.148 "
  cd ~/immocore &&
  git pull origin main &&
  docker compose -f docker-compose.prod.yml build --no-cache backend celery-worker celery-beat frontend &&
  docker compose -f docker-compose.prod.yml up -d &&
  sleep 5 &&
  docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --no-input
"
```

## Nur Frontend (kein Backend-Änderungen)

```bash
ssh -i "$USERPROFILE/.ssh/strato_server_key" -o StrictHostKeyChecking=no patrik@87.106.219.148 "
  cd ~/immocore &&
  git pull origin main &&
  docker compose -f docker-compose.prod.yml build frontend &&
  docker compose -f docker-compose.prod.yml up -d frontend
"
```

## Nur Backend (keine Frontend-Änderungen)

```bash
ssh -i "$USERPROFILE/.ssh/strato_server_key" -o StrictHostKeyChecking=no patrik@87.106.219.148 "
  cd ~/immocore &&
  git pull origin main &&
  docker compose -f docker-compose.prod.yml build backend celery-worker celery-beat &&
  docker compose -f docker-compose.prod.yml up -d backend celery-worker celery-beat &&
  sleep 5 &&
  docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --no-input
"
```

## Checkliste vor dem Deployment

- [ ] TypeScript-Fehler geprüft: `cd frontend && npx tsc --noEmit`
- [ ] Alle Änderungen committed und gepusht
- [ ] Neue Django-Modelle → Migration erstellt (`makemigrations`)
- [ ] Migration lokal getestet (`migrate`)

## Infos Server

| Eigenschaft | Wert |
|---|---|
| URL | http://87.106.219.148:8082 |
| SSH-User | `patrik` |
| SSH-Key | `~/.ssh/strato_server_key` |
| Projektpfad | `/home/patrik/immocore` |
| Compose-Datei | `docker-compose.prod.yml` |
| Env-Datei | `.env.prod` (nicht in Git) |

## Container-Status prüfen

```bash
ssh -i "$USERPROFILE/.ssh/strato_server_key" -o StrictHostKeyChecking=no patrik@87.106.219.148 \
  "docker compose -f ~/immocore/docker-compose.prod.yml ps 2>&1 | grep -v 'level=warning'"
```

## Logs anschauen

```bash
# Backend-Logs
ssh ... "docker logs immocore_backend --tail 50"

# Celery-Logs
ssh ... "docker logs immocore_celery_worker --tail 50"
```

## Notfall: Alle Container neu starten

```bash
ssh -i "$USERPROFILE/.ssh/strato_server_key" -o StrictHostKeyChecking=no patrik@87.106.219.148 "
  cd ~/immocore &&
  docker compose -f docker-compose.prod.yml down &&
  docker compose -f docker-compose.prod.yml up -d
"
```
