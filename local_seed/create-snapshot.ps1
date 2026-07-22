<#
.SYNOPSIS
  Nimmt einen neuen Seed-Snapshot vom AKTUELLEN Stand der lokalen DB auf
  und ueberschreibt local_seed\immocore_seed.sql.

.DESCRIPTION
  Verwende dies, wenn du den Basis-Stand aktualisieren willst -- z.B.
  nachdem neue Stammdaten dazugekommen sind oder du einen neuen sauberen
  Ausgangspunkt festhalten moechtest. Der bisherige Snapshot wird vorher
  mit Zeitstempel gesichert.

  Der Snapshot enthaelt ECHTE Personendaten und gehoert NICHT ins Git
  (durch .gitignore ausgeschlossen).

.EXAMPLE
  .\local_seed\create-snapshot.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$proj = Split-Path $PSScriptRoot -Parent
$seed = Join-Path $PSScriptRoot 'immocore_seed.sql'
$db   = 'immocore_db'

function Assert-LastExit($step) {
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen bei: $step (ExitCode $LASTEXITCODE)" }
}

Set-Location $proj

Write-Host "=== Immocore: Neuen Seed-Snapshot aufnehmen ===" -ForegroundColor Cyan

# Aktuelle Datensaetze zeigen (damit klar ist, was eingefroren wird)
Write-Host "Aktueller Stand der lokalen DB:"
docker compose exec -T db psql -U immocore -d immocore -c "select 'personen' t, count(*) from personen_person union all select 'objekte', count(*) from objekte_objekt union all select 'einheiten', count(*) from objekte_einheit union all select 'buchungen', count(*) from buchhaltung_buchung union all select 'rechnungen', count(*) from rechnungen_rechnung order by t;"

# Alten Snapshot sichern
if (Test-Path $seed) {
    $ts  = Get-Date -Format 'yyyyMMdd_HHmmss'
    $old = Join-Path $PSScriptRoot "immocore_seed_$ts.sql"
    Move-Item $seed $old
    Write-Host "Bisherigen Snapshot gesichert -> $old" -ForegroundColor Yellow
}

Write-Host "Neuen Snapshot aufnehmen ..."
docker compose exec -T db pg_dump -U immocore -d immocore --no-owner --no-privileges -f /tmp/_seed.sql
Assert-LastExit "pg_dump"
docker cp "$db`:/tmp/_seed.sql" "$seed"
Assert-LastExit "docker cp"
docker compose exec -T db rm -f /tmp/_seed.sql

$size = [math]::Round((Get-Item $seed).Length / 1MB, 1)
Write-Host ""
Write-Host "Fertig. Neuer Seed: $seed ($size MB)" -ForegroundColor Green
Write-Host "Zuruckspielen jederzeit mit: .\local_seed\reset-local-db.ps1"
