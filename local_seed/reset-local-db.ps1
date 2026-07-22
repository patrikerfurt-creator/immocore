<#
.SYNOPSIS
  Setzt die LOKALE Immocore-Datenbank auf den Seed-Snapshot zurueck
  (volle Stammdaten, keine Bewegungsdaten) und migriert danach auf den
  aktuellen Code-Stand.

.DESCRIPTION
  Ablauf:
    1. Sicherheitsbackup der aktuellen lokalen DB (ausser -NoBackup)
    2. App-Container stoppen (loest DB-Sperren)
    3. Schema komplett leeren
    4. Seed-Snapshot einspielen (Schema + Daten + Migrationsstand)
    5. Backend starten und 'manage.py migrate' ausfuehren
       -> neue Migrationen (neue Tabellen/Spalten) werden sauber ergaenzt
    6. Celery-Container starten, Datensaetze zur Kontrolle ausgeben

  NUR fuer die lokale Docker-Umgebung (docker-compose.yml). Ruehrt den
  Live-Server NICHT an.

.PARAMETER NoBackup
  Ueberspringt das Sicherheitsbackup vor dem Zuruecksetzen.

.EXAMPLE
  .\local_seed\reset-local-db.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoBackup
)

$ErrorActionPreference = 'Stop'

$proj = Split-Path $PSScriptRoot -Parent
$seed = Join-Path $PSScriptRoot 'immocore_seed.sql'
$db   = 'immocore_db'

function Assert-LastExit($step) {
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen bei: $step (ExitCode $LASTEXITCODE)" }
}

if (-not (Test-Path $seed)) { throw "Seed-Snapshot nicht gefunden: $seed" }
Set-Location $proj

Write-Host "=== Immocore: Lokale DB auf Seed zuruecksetzen ===" -ForegroundColor Cyan
Write-Host "Projekt : $proj"
Write-Host "Seed    : $seed"
Write-Host ""

# 1. Sicherheitsbackup
if (-not $NoBackup) {
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    $bk = Join-Path $PSScriptRoot "auto_backup_$ts.sql"
    Write-Host "[1/6] Sicherheitsbackup -> $bk"
    docker compose exec -T db pg_dump -U immocore -d immocore --no-owner --no-privileges -f /tmp/_bk.sql
    Assert-LastExit "Backup (pg_dump)"
    docker cp "$db`:/tmp/_bk.sql" "$bk"
    Assert-LastExit "Backup (docker cp)"
    docker compose exec -T db rm -f /tmp/_bk.sql
} else {
    Write-Host "[1/6] Sicherheitsbackup uebersprungen (-NoBackup)" -ForegroundColor Yellow
}

# 2. App-Container stoppen
Write-Host "[2/6] App-Container stoppen ..."
docker compose stop backend celery-worker celery-beat | Out-Null

# 3. Schema leeren
Write-Host "[3/6] Schema leeren ..."
docker compose exec -T db psql -U immocore -d immocore -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO immocore; GRANT ALL ON SCHEMA public TO public;"
Assert-LastExit "Schema leeren"

# 4. Seed einspielen
Write-Host "[4/6] Seed einspielen ..."
docker cp "$seed" "$db`:/tmp/_seed.sql"
Assert-LastExit "Seed kopieren (docker cp)"
docker compose exec -T db psql -U immocore -d immocore -q -v ON_ERROR_STOP=1 -f /tmp/_seed.sql
Assert-LastExit "Seed einspielen (psql)"
docker compose exec -T db rm -f /tmp/_seed.sql

# 5. Backend starten + migrieren
Write-Host "[5/6] Backend starten und migrieren ..."
docker compose start backend | Out-Null
Start-Sleep -Seconds 5
docker compose exec -T backend python manage.py migrate --no-input
Assert-LastExit "migrate"

# 6. Celery starten + Kontrolle
Write-Host "[6/6] Celery starten ..."
docker compose start celery-worker celery-beat | Out-Null

Write-Host ""
Write-Host "=== Datensaetze nach Reset ===" -ForegroundColor Cyan
docker compose exec -T db psql -U immocore -d immocore -c "select 'personen' t, count(*) from personen_person union all select 'objekte', count(*) from objekte_objekt union all select 'einheiten', count(*) from objekte_einheit union all select 'vertraege', count(*) from personen_eigentumsverhaeltnis union all select 'buchungen', count(*) from buchhaltung_buchung union all select 'rechnungen', count(*) from rechnungen_rechnung order by t;"

Write-Host ""
Write-Host "Fertig. Lokale DB steht auf dem Seed-Stand." -ForegroundColor Green
