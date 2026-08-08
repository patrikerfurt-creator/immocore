# ============================================================================
#  IMMOCORE — CAMT53-Uploader
# ----------------------------------------------------------------------------
#  Überwacht einen lokalen Ordner auf neue camt.053-Dateien (Bank-Export) und
#  lädt Kopien per scp auf den Server in den CamtDAT-Eingangsordner hoch, wo das
#  Backend (Management-Command `camt_watch`) sie automatisch importiert.
#
#  - Originale bleiben lokal liegen ("Kopien hochladen").
#  - Bereits hochgeladene Dateien werden über eine SHA256-Merkliste erkannt und
#    nicht erneut gesendet (auch nach Neustart / bei Umbenennung).
#  - Konfiguration komplett über eine .env-Datei (siehe camt_uploader.env.example).
#
#  Verwendung:
#     .\camt_uploader.ps1                 # Dauerbetrieb (Poll-Loop)
#     .\camt_uploader.ps1 -RunOnce        # einmalig alle offenen Dateien senden
#     .\camt_uploader.ps1 -EnvFile C:\pfad\meine.env
#
#  Als Dienst einrichten: siehe install-service.ps1
# ============================================================================
[CmdletBinding()]
param(
    # Pfad zur .env-Konfigurationsdatei (Standard: neben diesem Skript)
    [string]$EnvFile = (Join-Path $PSScriptRoot 'camt_uploader.env'),

    # Nur einmal alle offenen Dateien verarbeiten und beenden (für Tests / Cron)
    [switch]$RunOnce
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ── .env laden ──────────────────────────────────────────────────────────────
function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Konfigurationsdatei nicht gefunden: $Path`n" +
              "Bitte camt_uploader.env.example nach camt_uploader.env kopieren und anpassen."
    }
    $cfg = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $idx = $t.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $t.Substring(0, $idx).Trim()
        $val = $t.Substring($idx + 1).Trim()
        # Umschließende Anführungszeichen entfernen
        if ($val.Length -ge 2 -and (
                ($val.StartsWith('"') -and $val.EndsWith('"')) -or
                ($val.StartsWith("'") -and $val.EndsWith("'")))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $cfg[$key] = $val
    }
    return $cfg
}

function Get-Cfg {
    param([hashtable]$Cfg, [string]$Key, $Default = $null, [switch]$Required)
    if ($Cfg.ContainsKey($Key) -and $Cfg[$Key] -ne '') { return $Cfg[$Key] }
    if ($Required) { throw "Pflicht-Einstellung '$Key' fehlt in der .env-Datei." }
    return $Default
}

# ── Logging ─────────────────────────────────────────────────────────────────
$script:LogFile = $null

function Write-Log {
    param([string]$Message, [ValidateSet('INFO','OK','WARN','ERROR')][string]$Level = 'INFO')
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line  = "$stamp [$Level] $Message"

    # Konsole (farbig, wenn interaktiv)
    $color = @{ INFO='Gray'; OK='Green'; WARN='Yellow'; ERROR='Red' }[$Level]
    Write-Host $line -ForegroundColor $color

    # Datei (mit einfacher Größen-Rotation bei > 5 MB)
    if ($script:LogFile) {
        try {
            if ((Test-Path -LiteralPath $script:LogFile) -and
                ((Get-Item -LiteralPath $script:LogFile).Length -gt 5MB)) {
                $bak = "$($script:LogFile).1"
                if (Test-Path -LiteralPath $bak) { Remove-Item -LiteralPath $bak -Force }
                Move-Item -LiteralPath $script:LogFile -Destination $bak -Force
            }
            Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8
        } catch {
            Write-Host "  (Log-Schreibfehler: $($_.Exception.Message))" -ForegroundColor DarkRed
        }
    }
}

# ── Merkliste (State) ─────────────────────────────────────────────────────────
function Read-State {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        try {
            $obj = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
            $map = @{}
            if ($obj -and $obj.PSObject.Properties['uploaded']) {
                foreach ($p in $obj.uploaded.PSObject.Properties) {
                    $map[$p.Name] = $p.Value
                }
            }
            return $map
        } catch {
            Write-Log "Merkliste beschädigt, starte mit leerer Liste: $($_.Exception.Message)" WARN
        }
    }
    return @{}
}

function Save-State {
    param([hashtable]$State, [string]$Path)
    $wrapper = [ordered]@{ uploaded = [ordered]@{} }
    foreach ($k in ($State.Keys | Sort-Object)) { $wrapper.uploaded[$k] = $State[$k] }
    $tmp = "$Path.tmp"
    ($wrapper | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

# ── camt.053-Erkennung ────────────────────────────────────────────────────────
function Test-IsCamt053 {
    param([string]$Path)
    try {
        # Nur den Anfang lesen — camt.053 hat den Namespace im Wurzelelement
        $head = Get-Content -LiteralPath $Path -TotalCount 40 -Encoding UTF8 -ErrorAction Stop `
                | Select-Object -First 40
        return (($head -join "`n") -match 'camt\.053')
    } catch {
        return $false
    }
}

# ── Datei fertig geschrieben? ───────────────────────────────────────────────
function Test-FileStable {
    param([System.IO.FileInfo]$File, [int]$StableSeconds)
    # Datei muss seit mindestens $StableSeconds unverändert sein UND exklusiv
    # öffenbar (nicht mehr durch die Bank-Software gesperrt).
    if ((Get-Date).ToUniversalTime() - $File.LastWriteTimeUtc -lt [TimeSpan]::FromSeconds($StableSeconds)) {
        return $false
    }
    try {
        $fs = [System.IO.File]::Open($File.FullName, 'Open', 'Read', 'None')
        $fs.Close(); $fs.Dispose()
        return $true
    } catch {
        return $false
    }
}

# ── Native exe robust aufrufen (stderr nicht als terminierender Fehler) ────────
function Invoke-Native {
    param([string]$Exe, [string[]]$ExeArgs)
    # stderr in eine Temp-Datei umleiten (nicht 2>&1): so entsteht unter
    # $ErrorActionPreference='Stop' KEIN terminierender NativeCommandError.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        $stdout = & $Exe @ExeArgs 2>$errFile
        $code   = $LASTEXITCODE
        $stderr = ''
        if (Test-Path -LiteralPath $errFile) {
            $stderr = (Get-Content -LiteralPath $errFile -Raw)
        }
        $combined = ((@($stdout) + @($stderr)) -join "`n").Trim()
        return @{ ExitCode = $code; Output = $combined }
    } finally {
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
        $ErrorActionPreference = $prev
    }
}

# ── Upload per scp (+ atomare Umbenennung auf dem Server) ──────────────────────
function Send-CamtFile {
    param(
        [System.IO.FileInfo]$File,
        [hashtable]$S   # Settings
    )

    # Temporäre Endung, die camt_watch NICHT als *.xml erkennt → kein Zugriff auf
    # halb übertragene Dateien. Nach Erfolg atomar umbenennen.
    $remoteFinal = "$($S.RemoteDir)/$($File.Name)"
    $remoteTmp   = "$($File.Name).uploading"
    $remoteTmpFull = "$($S.RemoteDir)/$remoteTmp"

    $sshOpts = @(
        '-i', $S.SshKey,
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', "UserKnownHostsFile=$($S.KnownHostsFile)",
        '-o', 'ConnectTimeout=20'
    )

    # 1) Hochladen unter temporärem Namen (CAMT-Dateinamen enthalten keine Leerzeichen)
    $target = '{0}@{1}:{2}' -f $S.SshUser, $S.SshHost, $remoteTmpFull
    $r = Invoke-Native -Exe 'scp' -Args ($sshOpts + @($File.FullName, $target))
    if ($r.ExitCode -ne 0) {
        Write-Log "scp fehlgeschlagen für $($File.Name): $($r.Output)" ERROR
        return $false
    }

    # 2) Atomar auf finalen Namen umbenennen (camt_watch greift erst jetzt zu)
    $mvCmd = "mv -f -- '$remoteTmpFull' '$remoteFinal'"
    $r = Invoke-Native -Exe 'ssh' -Args ($sshOpts + @(('{0}@{1}' -f $S.SshUser, $S.SshHost), $mvCmd))
    if ($r.ExitCode -ne 0) {
        Write-Log "Umbenennen auf Server fehlgeschlagen für $($File.Name): $($r.Output)" ERROR
        return $false
    }

    return $true
}

# ── Ein Verarbeitungsdurchlauf ─────────────────────────────────────────────────
function Invoke-Scan {
    param([hashtable]$S, [hashtable]$State)

    $dateien = Get-ChildItem -LiteralPath $S.WatchFolder -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Extension -in $S.Extensions }

    $neu = 0
    foreach ($f in ($dateien | Sort-Object Name)) {
        if (-not (Test-FileStable -File $f -StableSeconds $S.StableSeconds)) {
            continue  # noch in Bearbeitung — nächster Durchlauf
        }

        if ($S.ValidateCamt -and -not (Test-IsCamt053 -Path $f.FullName)) {
            Write-Log "Übersprungen (kein camt.053): $($f.Name)" WARN
            continue
        }

        $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
        if ($State.ContainsKey($hash)) {
            continue  # bereits hochgeladen
        }

        Write-Log "Neue Datei: $($f.Name) ($([math]::Round($f.Length/1KB,1)) KB) → Upload…"
        if (Send-CamtFile -File $f -S $S) {
            $State[$hash] = [ordered]@{
                name       = $f.Name
                size       = $f.Length
                uploadedAt = (Get-Date).ToString('o')
            }
            Save-State -State $State -Path $S.StateFile
            Write-Log "Hochgeladen: $($f.Name) → $($S.SshHost):$($S.RemoteDir)/" OK
            $neu++
        }
        # Bei Fehler: kein State-Eintrag → wird im nächsten Durchlauf erneut versucht
    }
    return $neu
}

# ============================================================================
#  Hauptprogramm
# ============================================================================
$cfg = Import-DotEnv -Path $EnvFile

$S = @{
    WatchFolder    = (Get-Cfg $cfg 'WATCH_FOLDER' -Required)
    SshHost        = (Get-Cfg $cfg 'SSH_HOST'     -Required)
    SshUser        = (Get-Cfg $cfg 'SSH_USER'     -Required)
    SshKey         = (Get-Cfg $cfg 'SSH_KEY'      -Required)
    RemoteDir      = (Get-Cfg $cfg 'REMOTE_DIR'   -Required)
    PollInterval   = [int](Get-Cfg $cfg 'POLL_INTERVAL' 60)
    StableSeconds  = [int](Get-Cfg $cfg 'STABLE_SECONDS' 5)
    ValidateCamt   = ([string](Get-Cfg $cfg 'VALIDATE_CAMT' 'true')).ToLower() -in @('1','true','yes','ja')
}
$S.Extensions   = (Get-Cfg $cfg 'FILE_EXTENSIONS' '.xml') -split ',' |
                  ForEach-Object { $e = $_.Trim().ToLower(); if ($e -and -not $e.StartsWith('.')) { ".$e" } else { $e } } |
                  Where-Object { $_ }
$S.StateFile      = (Get-Cfg $cfg 'STATE_FILE' (Join-Path $S.WatchFolder '.camt_uploader_state.json'))
$S.KnownHostsFile = (Get-Cfg $cfg 'KNOWN_HOSTS_FILE' (Join-Path $PSScriptRoot 'known_hosts'))
$logFileCfg       = (Get-Cfg $cfg 'LOG_FILE' (Join-Path $PSScriptRoot 'logs\camt_uploader.log'))

# Log-Verzeichnis anlegen
$logDir = Split-Path -Parent $logFileCfg
if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$script:LogFile = $logFileCfg

# Validierungen
if (-not (Test-Path -LiteralPath $S.WatchFolder)) {
    throw "WATCH_FOLDER existiert nicht: $($S.WatchFolder)"
}
if (-not (Test-Path -LiteralPath $S.SshKey)) {
    throw "SSH_KEY nicht gefunden: $($S.SshKey)"
}
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp nicht gefunden. Bitte OpenSSH-Client installieren (Windows-Feature oder Git for Windows)."
}

Write-Log "===== CAMT53-Uploader gestartet =====" OK
Write-Log "Watch-Ordner : $($S.WatchFolder)"
Write-Log "Ziel         : $($S.SshUser)@$($S.SshHost):$($S.RemoteDir)"
Write-Log "Endungen     : $($S.Extensions -join ', ')  | camt.053-Prüfung: $($S.ValidateCamt)"
Write-Log "Merkliste    : $($S.StateFile)"
Write-Log "Intervall    : $($S.PollInterval)s  | RunOnce: $RunOnce"

$state = Read-State -Path $S.StateFile
Write-Log "Merkliste geladen: $($state.Count) bereits hochgeladene Datei(en)."

if ($RunOnce) {
    $n = Invoke-Scan -S $S -State $state
    Write-Log "Einmal-Durchlauf beendet: $n neue Datei(en) hochgeladen." OK
    return
}

Write-Log "Dauerbetrieb — Prüfe alle $($S.PollInterval)s auf neue Dateien. (Beenden: Strg+C)"
while ($true) {
    try {
        Invoke-Scan -S $S -State $state | Out-Null
    } catch {
        Write-Log "Unerwarteter Fehler im Durchlauf: $($_.Exception.Message)" ERROR
    }
    Start-Sleep -Seconds $S.PollInterval
}
