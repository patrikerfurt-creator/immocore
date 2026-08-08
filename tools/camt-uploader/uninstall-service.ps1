# ============================================================================
#  IMMOCORE CAMT53-Uploader — geplante Aufgabe wieder entfernen
#  ► In einer ADMIN-PowerShell ausführen:  .\uninstall-service.ps1
# ============================================================================
[CmdletBinding()]
param(
    [string]$TaskName = 'IMMOCORE CAMT53 Uploader'
)

$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent() `
           ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    throw "Bitte in einer PowerShell MIT Administratorrechten ausführen."
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask  -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ Aufgabe '$TaskName' entfernt." -ForegroundColor Green
} else {
    Write-Host "Keine Aufgabe '$TaskName' gefunden." -ForegroundColor Yellow
}
