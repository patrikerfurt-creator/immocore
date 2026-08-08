# IMMOCORE — CAMT53-Uploader

Kleines Windows-Tool, das einen lokalen Ordner überwacht und neue
**camt.053**-Dateien (Bank-Kontoauszüge) automatisch auf den IMMOCORE-Server
in den Eingangsordner `CamtDAT` hochlädt. Dort holt sie das Backend
(Management-Command `camt_watch`) automatisch ab und importiert die Umsätze.

```
 Bank-Export  ──►  lokaler Watch-Ordner  ──scp──►  Server /home/patrik/immocore/CamtDAT
                        (dieses Tool)                          │
                                                               ▼
                                                   camt_watch  →  Import in DB
                                                   (archiv/ · fehler/)
```

## Eigenschaften

- **Originale bleiben liegen** — es werden nur Kopien hochgeladen.
- **Kein Doppel-Upload** — bereits gesendete Dateien werden über eine
  SHA256-Merkliste (`.camt_uploader_state.json`) erkannt, auch nach Neustart.
- **Sicherer Upload** — Dateien werden erst unter `*.uploading` übertragen und
  dann atomar umbenannt, damit `camt_watch` nie halb übertragene Dateien sieht.
- **camt.053-Prüfung** — es werden nur echte camt.053-XMLs gesendet (abschaltbar).
- **Läuft als Dienst** — via Windows-Aufgabenplanung, Autostart beim Booten,
  automatischer Neustart bei Fehlern.

## Voraussetzungen

- Windows mit **OpenSSH-Client** (`ssh`/`scp`) — bei Windows 10/11 vorhanden,
  ansonsten über Git for Windows oder das optionale Windows-Feature.
- Der SSH-Key für den Server (`strato_server_key`), passwortlos nutzbar.

## Einrichtung

1. **Konfiguration anlegen**

   ```powershell
   cd C:\Projekte\immocore\tools\camt-uploader
   Copy-Item camt_uploader.env.example camt_uploader.env
   notepad camt_uploader.env
   ```

   Mindestens `WATCH_FOLDER` auf den Ordner setzen, in den die Bank-Software
   exportiert. Server-Daten sind bereits vorausgefüllt.

2. **Testlauf im Vordergrund** (zeigt alles in der Konsole):

   ```powershell
   .\camt_uploader.ps1 -RunOnce      # sendet einmalig alle offenen Dateien
   .\camt_uploader.ps1               # Dauerbetrieb, Beenden mit Strg+C
   ```

3. **Als Dienst registrieren** (PowerShell **als Administrator**):

   ```powershell
   .\install-service.ps1
   Start-ScheduledTask -TaskName 'IMMOCORE CAMT53 Uploader'   # sofort starten
   ```

   Standardmäßig läuft die Aufgabe als **SYSTEM** (kein Passwort nötig).
   Alternativ als eigener Benutzer:

   ```powershell
   .\install-service.ps1 -RunAsUser "$env:USERDOMAIN\$env:USERNAME"
   ```

## Betrieb & Diagnose

```powershell
# Status der Aufgabe
Get-ScheduledTask -TaskName 'IMMOCORE CAMT53 Uploader' | Get-ScheduledTaskInfo

# Live-Log
Get-Content .\logs\camt_uploader.log -Tail 30 -Wait

# Serverseitig prüfen, ob Dateien ankommen / importiert werden
ssh -i C:\Users\maurer\.ssh\strato_server_key patrik@87.106.219.148 `
    "ls -l ~/immocore/CamtDAT ~/immocore/CamtDAT/archiv | tail"
```

Damit importiert wird, muss auf dem Server der Watcher laufen:

```bash
docker exec -d immocore_backend python manage.py camt_watch --ordner /app/camt_dat
```

## Entfernen

```powershell
.\uninstall-service.ps1
```

## Konfigurationsreferenz (`camt_uploader.env`)

| Schlüssel          | Bedeutung                                                      | Standard |
|--------------------|----------------------------------------------------------------|----------|
| `WATCH_FOLDER`     | Lokaler Ordner, der überwacht wird                             | —        |
| `SSH_HOST`         | Server-IP/Host                                                 | —        |
| `SSH_USER`         | SSH-Benutzer                                                   | —        |
| `SSH_KEY`          | Pfad zum privaten SSH-Key                                      | —        |
| `REMOTE_DIR`       | Zielordner auf dem Server (`CamtDAT`)                          | —        |
| `POLL_INTERVAL`    | Prüfintervall in Sekunden                                      | 60       |
| `STABLE_SECONDS`   | Ruhezeit, bevor eine Datei als fertig gilt                     | 5        |
| `FILE_EXTENSIONS`  | Berücksichtigte Endungen (kommagetrennt)                      | `.xml`   |
| `VALIDATE_CAMT`    | Nur Dateien mit Inhalt „camt.053" senden                       | true     |
| `STATE_FILE`       | Pfad der SHA256-Merkliste                                      | im Watch-Ordner |
| `KNOWN_HOSTS_FILE` | known_hosts für die SSH-Verbindung                            | im Tool-Ordner |
| `LOG_FILE`         | Pfad der Logdatei                                              | `logs\camt_uploader.log` |
