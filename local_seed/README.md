# Lokaler DB-Seed

Ein wiederverwendbarer Snapshot der **lokalen** Immocore-Datenbank:
volle Stammdaten (Personen, Objekte, Einheiten, Verträge, Kontenrahmen,
Hausgeld-Historie), aber **keine Bewegungsdaten** (keine Buchungen,
Sollstellungen, Rechnungen, Dokumente).

Damit kannst du deine lokale DB jederzeit auf einen sauberen, gefüllten
Ausgangsstand zurücksetzen und neu ausprobieren.

> ⚠️ Der Snapshot enthält **echte Personendaten aus dem Live-System**.
> Er ist per `.gitignore` vom Git ausgeschlossen und darf nirgends
> hochgeladen oder weitergegeben werden.

## Dateien

| Datei | Zweck |
|-------|-------|
| `immocore_seed.sql`     | Der aktuelle Seed-Snapshot |
| `reset-local-db.ps1`    | Spielt den Seed ein + migriert auf aktuellen Code-Stand |
| `create-snapshot.ps1`   | Nimmt einen neuen Seed vom aktuellen DB-Stand auf |
| `auto_backup_*.sql`     | Automatische Sicherung vor jedem Reset |
| `immocore_seed_*.sql`   | Frühere Snapshots (bei `create-snapshot` gesichert) |

## Verwendung (PowerShell, im Projektordner)

**Lokale DB auf den Seed zurücksetzen:**
```powershell
.\local_seed\reset-local-db.ps1
```

**Ohne Sicherheitsbackup (schneller):**
```powershell
.\local_seed\reset-local-db.ps1 -NoBackup
```

**Neuen Basis-Stand festhalten** (z. B. nachdem neue Stammdaten dazukamen):
```powershell
.\local_seed\create-snapshot.ps1
```

## Warum das auch nach Code-/Schema-Änderungen funktioniert

Der Snapshot speichert das **komplette Schema samt Migrationsstand**
(`django_migrations`). `reset-local-db.ps1` spielt zuerst den Snapshot ein
und führt **danach `manage.py migrate`** aus. Sind seit dem Snapshot neue
Migrationen dazugekommen (neue Tabellen, Spalten, Umbenennungen), werden
diese sauber angewendet — die vorhandenen Stammdaten bleiben erhalten.

Wenn sich der Stammdaten-Umfang dauerhaft ändert und du den neuen Stand
als Basis willst, nimm mit `create-snapshot.ps1` einfach einen neuen
Snapshot auf.

## Wichtig

- Skripte betreffen **nur die lokale Docker-Umgebung** (`docker-compose.yml`).
  Der Live-Server wird nie angefasst.
- Voraussetzung: Die lokalen Container laufen (`docker compose up -d`).
