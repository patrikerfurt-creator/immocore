# IMMOCORE — Serverkonfiguration

**Erstellt:** 2026-06-04  
**Autor:** Claude Code / Demme Immobilien GmbH

---

## Server-Eckdaten

| Eigenschaft        | Wert                          |
|--------------------|-------------------------------|
| **Anbieter**       | Strato AG                     |
| **Paket**          | VPS Linux VC2-4 (a.LZ12)      |
| **IP-Adresse**     | 87.106.219.148                |
| **Betriebssystem** | Ubuntu 22.04.5 LTS (Jammy)    |
| **Kernel**         | 5.15.0-179-generic            |
| **CPU**            | 2 vCores                      |
| **RAM**            | 3,8 GB                        |
| **Speicher**       | 117 GB SSD (14 GB belegt)     |
| **Docker**         | 29.2.1                        |
| **Docker Compose** | 5.0.2                         |

---

## Zugang

### SSH
```bash
ssh -i $env:USERPROFILE\.ssh\strato_server_key patrik@87.106.219.148
```

| Eigenschaft     | Wert                          |
|-----------------|-------------------------------|
| **Benutzer**    | `patrik`                      |
| **Gruppe**      | sudo, docker                  |
| **SSH-Key**     | `~/.ssh/strato_server_key`    |
| **Root-Zugang** | via `sudo` (Passwort erforderlich) |

### Anwendung
| URL                           | Beschreibung              |
|-------------------------------|---------------------------|
| http://87.106.219.148:8082    | IMMOCORE Frontend (live)  |
| http://87.106.219.148:8082/admin/ | Django Admin          |

**Login:** Benutzername `admin` — Passwort in `admin.txt` im Projektverzeichnis

---

## Projektverzeichnis

```
/home/patrik/immocore/        ← Projektroot
├── docker-compose.prod.yml   ← Produktions-Compose
├── .env.prod                 ← Umgebungsvariablen (NICHT in Git)
├── deploy.sh                 ← Update-Skript
├── backend/                  ← Django-Anwendung
├── frontend/                 ← React-Anwendung
├── CamtDAT/                  ← CAMT-Eingangsordner (automatisch überwacht)
│   ├── archiv/               ← verarbeitete CAMT-Dateien
│   └── fehler/               ← fehlerhafte CAMT-Dateien
└── Rechnungen/               ← Rechnungs-Eingangsordner (automatisch überwacht)
    ├── archiv/               ← verarbeitete Rechnungen
    └── fehler/               ← fehlerhafte Rechnungen
```

---

## Docker-Container

Alle Container laufen unter `~/immocore` mit `docker-compose.prod.yml`.

| Container               | Image                  | Port (intern) | Port (extern) | Beschreibung              |
|-------------------------|------------------------|---------------|---------------|---------------------------|
| `immocore_frontend`     | immocore-frontend      | 80            | **8082**      | React-App via nginx       |
| `immocore_backend`      | immocore-backend       | 8000          | —             | Django + Gunicorn (3 Worker) |
| `immocore_celery_worker`| immocore-celery-worker | —             | —             | Hintergrundaufgaben       |
| `immocore_celery_beat`  | immocore-celery-beat   | —             | —             | Zeitgesteuerte Tasks      |
| `immocore_db`           | postgres:16-alpine     | 5432          | —             | PostgreSQL-Datenbank      |
| `immocore_redis`        | redis:7-alpine         | 6379          | —             | Cache / Task-Queue        |

> DB, Redis und Backend sind **nicht** von außen erreichbar — nur intern im Docker-Netzwerk.

---

## Weitere Anwendungen auf dem Server

| Container             | Port extern | Beschreibung            |
|-----------------------|-------------|-------------------------|
| `messdienst-nginx-1`  | **80**      | Messdienst-App (belegt Port 80) |
| `messdienst-web-1`    | —           | Messdienst Backend      |
| `messdienst-db-1`     | —           | Messdienst Datenbank    |
| `demre-frontend-1`    | **8081**    | DEMRE-Frontend          |
| `demre-backend-1`     | —           | DEMRE-Backend           |
| `demre-db-1`          | —           | DEMRE-Datenbank         |

> IMMOCORE läuft deshalb auf Port **8082** (nicht 80).

---

## Umgebungsvariablen (.env.prod)

Datei liegt auf dem Server unter `~/immocore/.env.prod` — **nicht in Git**.

```env
SECRET_KEY=<langer Zufallsstring — nur auf dem Server>
DEBUG=False

DB_NAME=immocore
DB_USER=immocore
DB_PASSWORD=<nur auf dem Server>
DB_HOST=db
DB_PORT=5432

POSTGRES_DB=immocore
POSTGRES_USER=immocore
POSTGRES_PASSWORD=<nur auf dem Server>

ALLOWED_HOSTS=87.106.219.148
CORS_ALLOWED_ORIGINS=http://87.106.219.148
CSRF_TRUSTED_ORIGINS=http://87.106.219.148

REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=<falls vorhanden>
```

> Bei Domain-Umstellung (HTTPS) müssen `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` und  
> `CSRF_TRUSTED_ORIGINS` auf die neue Domain aktualisiert werden.

---

## Produktions-Dockerfiles

| Datei                          | Beschreibung                                      |
|--------------------------------|---------------------------------------------------|
| `backend/Dockerfile.prod`      | Python 3.11-slim + WeasyPrint + Gunicorn          |
| `frontend/Dockerfile.prod`     | Multi-Stage: node:20-alpine → nginx:alpine        |
| `frontend/nginx-frontend.conf` | nginx: SPA-Routing + API-Proxy zu Django          |

---

## Updates einspielen

```bash
# Per SSH einloggen
ssh -i ~/.ssh/strato_server_key patrik@87.106.219.148

# Deployment-Skript ausführen
cd ~/immocore
bash deploy.sh
```

Das Skript führt automatisch aus:
1. `git pull origin main`
2. `docker compose build --no-cache`
3. `docker compose up -d`
4. `python manage.py migrate`
5. `python manage.py collectstatic`

---

## Nützliche Befehle (auf dem Server)

```bash
# Status aller Container
docker compose -f ~/immocore/docker-compose.prod.yml ps

# Logs anzeigen (z.B. Backend)
docker logs immocore_backend --tail 50 -f

# Django Shell
docker exec -it immocore_backend python manage.py shell

# Datenbank-Backup
docker exec immocore_db pg_dump -U immocore immocore > backup_$(date +%Y%m%d).sql

# Alle Container neu starten
docker compose -f ~/immocore/docker-compose.prod.yml restart
```

---

## Offene Punkte / Empfehlungen

| Priorität | Aufgabe                                                                 |
|-----------|-------------------------------------------------------------------------|
| 🔴 Hoch   | **HTTPS einrichten** — Domain + Let's Encrypt SSL-Zertifikat            |
| 🔴 Hoch   | **Admin-Passwort ändern** nach erstem Login                             |
| 🟡 Mittel | **Automatisches DB-Backup** einrichten (täglich, z.B. via Cron)        |
| 🟡 Mittel | **Swap einrichten** — aktuell kein Swap aktiv (3,8 GB RAM ohne Puffer) |
| 🟢 Niedrig | Domain-Konfiguration: `immocore.demme-immobilien.de`                  |
| 🟢 Niedrig | Firewall (ufw) konfigurieren — nur Ports 80, 443, 8081, 8082, 22 offen |
