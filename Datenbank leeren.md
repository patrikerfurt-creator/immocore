# Datenbank leeren (lokal auf Stammdaten zurücksetzen)

Ziel: Lokale DB auf einen Zustand zurücksetzen, der alle Stammdaten enthält (Objekte, Personen, Einheiten, Verträge, Kontenrahmen, Hausgeld-Historie), aber **keine** Bewegungsdaten (keine Buchungen, Sollstellungen, Rechnungen, Dokumente, WKZ).

Dafür existiert bereits ein wiederverwendbarer Mechanismus unter `local_seed/`.

## Vorhandene Dateien

- **`immocore_seed.sql`** — der DB-Snapshot (Schema + Daten + `django_migrations`). Stand: 22.07.2026, ursprünglich aus dem Live-Klon abgeleitet. Enthält echte Personendaten → per `.gitignore` von Git ausgeschlossen, niemals hochladen.
- **`reset-local-db.ps1`** — spielt den Seed in die lokale DB ein und führt danach `manage.py migrate` aus, damit auch neuere Migrationen berücksichtigt werden. Optional mit `-NoBackup`. Legt sonst automatisch ein `auto_backup_*.sql` an, bevor zurückgesetzt wird.
- **`create-snapshot.ps1`** — nimmt einen neuen Seed vom aktuellen DB-Stand auf (sichert den alten Snapshot mit Zeitstempel ab).
- **`README.md`** — Kurzanleitung direkt im Ordner.

## Ablauf

1. Nur die lokale Docker-Umgebung ist betroffen (`docker-compose.yml`, Container `immocore_db` / `immocore_backend`). **Live wird nie angefasst.**
2. Reset auf den gespeicherten Stammdaten-Snapshot:
   ```powershell
   cd local_seed
   ./reset-local-db.ps1
   ```
3. Danach ist die lokale DB wieder im "leeren" Ausgangszustand: volle Stammdaten, keine Bewegungsdaten.

## Wenn sich die Stammdaten geändert haben

Falls seit dem 22.07. neue Objekte, Personen oder Verträge angelegt wurden, die im aktuellen Snapshot fehlen: vor dem nächsten Reset einen neuen Snapshot aufnehmen, damit der neue Stammdaten-Stand als Ausgangspunkt dient:

```powershell
cd local_seed
./create-snapshot.ps1
```

## Hinweise

- Datei-Transfer in den Skripten läuft über `docker cp` (PowerShell-/BOM-sicher).
- `immocore_seed.sql` enthält echte Personendaten und darf nie ins Git.
