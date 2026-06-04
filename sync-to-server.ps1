# sync-to-server.ps1
# Überwacht lokale Ordner und überträgt neue Dateien automatisch zum Strato-Server.
#
# Starten:  .\sync-to-server.ps1
# Beenden:  Strg+C im Terminal

$SSH_KEY    = "$env:USERPROFILE\.ssh\strato_server_key"
$SSH_USER   = "patrik"
$SSH_HOST   = "87.106.219.148"

$LOKALE_ORDNER = @{
    "CamtDAT"    = @{
        lokal  = "$PSScriptRoot\CamtDAT"
        server = "/home/patrik/immocore/CamtDAT"
        filter = "*.xml"
    }
    "Rechnungen" = @{
        lokal  = "$PSScriptRoot\Rechnungen"
        server = "/home/patrik/immocore/Rechnungen"
        filter = "*.pdf;*.PDF"
    }
}

function Send-Datei($lokalpfad, $serverpfad, $name) {
    Write-Host "[$name] Übertrage: $(Split-Path $lokalpfad -Leaf)" -ForegroundColor Cyan
    $ziel = "${SSH_USER}@${SSH_HOST}:${serverpfad}/"
    $ergebnis = & scp -i $SSH_KEY -o StrictHostKeyChecking=no $lokalpfad $ziel 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$name] ✅ Erfolgreich übertragen: $(Split-Path $lokalpfad -Leaf)" -ForegroundColor Green
        return $true
    } else {
        Write-Host "[$name] ❌ Fehler beim Übertragen: $ergebnis" -ForegroundColor Red
        return $false
    }
}

function Start-Watcher($name, $config) {
    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path   = $config.lokal
    $watcher.Filter = "*.*"
    $watcher.IncludeSubdirectories = $false
    $watcher.EnableRaisingEvents   = $true

    $erlaubteEndungen = $config.filter -split ";" | ForEach-Object { $_.Trim().ToLower().TrimStart("*") }

    $action = {
        $pfad   = $Event.SourceEventArgs.FullPath
        $endung = [System.IO.Path]::GetExtension($pfad).ToLower()

        # Nur erlaubte Dateitypen
        if ($endung -notin $using:erlaubteEndungen) { return }

        # Kurz warten bis Datei fertig geschrieben ist
        Start-Sleep -Seconds 1

        # Prüfen ob Datei lesbar ist (nicht noch in Benutzung)
        $versuche = 0
        while ($versuche -lt 5) {
            try {
                $stream = [System.IO.File]::Open($pfad, 'Open', 'Read', 'None')
                $stream.Close()
                break
            } catch {
                $versuche++
                Start-Sleep -Seconds 2
            }
        }

        Send-Datei $pfad $using:config.server $using:name | Out-Null
    }

    Register-ObjectEvent $watcher "Created" -Action $action -SourceIdentifier "Watcher_$name" | Out-Null
    Write-Host "[$name] 👁  Überwache: $($config.lokal)" -ForegroundColor Yellow
    return $watcher
}

# ── Start ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor White
Write-Host "║   IMMOCORE — Datei-Sync zum Server       ║" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor White
Write-Host ""

# Ordner auf dem Server sicherstellen
foreach ($name in $LOKALE_ORDNER.Keys) {
    $config = $LOKALE_ORDNER[$name]

    # Lokaler Ordner
    if (-not (Test-Path $config.lokal)) {
        New-Item -ItemType Directory -Path $config.lokal | Out-Null
        Write-Host "[$name] Lokaler Ordner angelegt: $($config.lokal)" -ForegroundColor Gray
    }

    # Server-Ordner
    & ssh -i $SSH_KEY -o StrictHostKeyChecking=no "${SSH_USER}@${SSH_HOST}" "mkdir -p $($config.server)" 2>$null
}

Write-Host ""

# Noch nicht übertragene Dateien beim Start übertragen
Write-Host "Prüfe auf vorhandene Dateien..." -ForegroundColor Gray
foreach ($name in $LOKALE_ORDNER.Keys) {
    $config  = $LOKALE_ORDNER[$name]
    $endungen = $config.filter -split ";" | ForEach-Object { $_.Trim().TrimStart("*") }

    Get-ChildItem -Path $config.lokal -File | Where-Object {
        $endungen -contains $_.Extension -or $endungen -contains $_.Extension.ToLower()
    } | ForEach-Object {
        Send-Datei $_.FullName $config.server $name | Out-Null
    }
}

# Watcher starten
$watchers = @()
foreach ($name in $LOKALE_ORDNER.Keys) {
    $watchers += Start-Watcher $name $LOKALE_ORDNER[$name]
}

Write-Host ""
Write-Host "Bereit — Dateien in die Ordner legen zum Übertragen." -ForegroundColor Green
Write-Host "Beenden mit Strg+C" -ForegroundColor Gray
Write-Host ""

# Laufen lassen bis Strg+C
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    foreach ($name in $LOKALE_ORDNER.Keys) {
        Unregister-Event -SourceIdentifier "Watcher_$name" -ErrorAction SilentlyContinue
    }
    $watchers | ForEach-Object { $_.Dispose() }
    Write-Host "`nSync beendet." -ForegroundColor Gray
}
