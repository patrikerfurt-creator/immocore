# ============================================================================
#  IMMOCORE CAMT53-Uploader — als Windows-Dienst (Aufgabenplanung) einrichten
# ----------------------------------------------------------------------------
#  Registriert eine geplante Aufgabe, die camt_uploader.ps1 beim Systemstart
#  im Hintergrund startet und bei Fehlern automatisch neu startet.
#
#  ► In einer ADMIN-PowerShell ausführen:
#        .\install-service.ps1
#
#  Standardmäßig läuft die Aufgabe als SYSTEM (kein Passwort nötig, kein
#  angemeldeter Benutzer erforderlich). Der SSH-Key muss dann für SYSTEM
#  lesbar sein (weltlesbar reicht) — das ist bei strato_server_key der Fall.
#
#  Alternativ als eigener Benutzer:
#        .\install-service.ps1 -RunAsUser "$env:USERDOMAIN\$env:USERNAME"
#    (Passwort wird beim Registrieren abgefragt.)
# ============================================================================
[CmdletBinding()]
param(
    [string]$TaskName = 'IMMOCORE CAMT53 Uploader',
    [string]$RunAsUser,                      # leer = SYSTEM
    [string]$EnvFile                          # optional: abweichende .env
)

$ErrorActionPreference = 'Stop'

# Admin-Check
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent() `
           ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    throw "Bitte in einer PowerShell MIT Administratorrechten ausführen."
}

$scriptDir  = $PSScriptRoot
$mainScript = Join-Path $scriptDir 'camt_uploader.ps1'
if (-not (Test-Path -LiteralPath $mainScript)) {
    throw "camt_uploader.ps1 nicht gefunden neben install-service.ps1."
}

# .env muss existieren (sonst startet der Dienst nicht sauber)
$envPath = if ($EnvFile) { $EnvFile } else { Join-Path $scriptDir 'camt_uploader.env' }
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Konfigurationsdatei fehlt: $envPath`n" +
          "Bitte zuerst camt_uploader.env.example nach camt_uploader.env kopieren und anpassen."
}

# Aktion: PowerShell versteckt, Skript mit .env starten
$argLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
           "-File `"$mainScript`" -EnvFile `"$envPath`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine -WorkingDirectory $scriptDir

# Trigger: beim Systemstart
$trigger = New-ScheduledTaskTrigger -AtStartup

# Einstellungen: unbegrenzte Laufzeit, Auto-Neustart bei Fehler
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

# Principal: SYSTEM oder benannter Benutzer
if ([string]::IsNullOrWhiteSpace($RunAsUser)) {
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $cred = $null
    Write-Host "Aufgabe läuft als: SYSTEM" -ForegroundColor Cyan
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Password -RunLevel Highest
    $cred = Get-Credential -UserName $RunAsUser -Message "Passwort für $RunAsUser (Ausführung der geplanten Aufgabe)"
    Write-Host "Aufgabe läuft als: $RunAsUser" -ForegroundColor Cyan
}

# Bestehende Aufgabe entfernen
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Vorhandene Aufgabe '$TaskName' wird ersetzt…" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$regParams = @{
    TaskName    = $TaskName
    Action      = $action
    Trigger     = $trigger
    Settings    = $settings
    Principal   = $principal
    Description = 'Überwacht einen lokalen Ordner und lädt neue camt.053-Dateien zum IMMOCORE-Server (CamtDAT).'
}
if ($cred) {
    Register-ScheduledTask @regParams -User $RunAsUser -Password $cred.GetNetworkCredential().Password | Out-Null
} else {
    Register-ScheduledTask @regParams | Out-Null
}

Write-Host ""
Write-Host "✅ Aufgabe '$TaskName' registriert." -ForegroundColor Green
Write-Host "   Sie startet automatisch beim nächsten Systemstart." -ForegroundColor Gray
Write-Host ""
Write-Host "Jetzt sofort starten:" -ForegroundColor Cyan
Write-Host "   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Status prüfen:" -ForegroundColor Cyan
Write-Host "   Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "Log ansehen:" -ForegroundColor Cyan
Write-Host "   Get-Content '$($scriptDir)\logs\camt_uploader.log' -Tail 30 -Wait"
