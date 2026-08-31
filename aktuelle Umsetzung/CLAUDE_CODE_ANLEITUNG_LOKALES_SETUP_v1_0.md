# CLAUDE CODE — IMMOCORE
## Lokale Testumgebung: Mandantenfähigkeit & Mini-Portal (Setup-Anleitung)

**Version:** 1.0
**Stand:** August 2026
**Status:** 🟡 Bereit zur Umsetzung
**Bezug:** `CLAUDE_CODE_ANLEITUNG_MANDANTENFAEHIGKEIT_v1_0.md` (Spec 0), `CLAUDE_CODE_ANLEITUNG_WEG_PORTAL_MINI_v1_0.md` (Spec 1a)

---

## 0. Orchestrierung

**Orchestrator: Opus.**
Diese Anleitung ist überwiegend mechanische Konfigurationsarbeit — der Orchestrator prüft nur, ob die Verifikation in Kap. 5 vollständig grün ist, bevor Spec 0 selbst als lokal getestet gilt.

**Sub-Agenten:**

| Agent | Modell | Aufgabe |
|---|---|---|
| `immo-builder` | Sonnet | Settings-Anpassungen, Tenant-Anlage, `.env`-Ergänzungen, CORS-Konfiguration |
| `immo-explorer` | Haiku | Verifikation nach jedem Schritt (Kap. 5) — read-only Prüfung, dass die Isolation zwischen den beiden Test-Mandanten tatsächlich greift |

Kein `immo-architect` nötig — keine offenen Architekturfragen in diesem Schritt, reine Umsetzung der bereits getroffenen Entscheidungen aus Spec 0 und Spec 1a.

---

## 1. Ziel

Eine lokale Umgebung, in der sich Spec 0 (Mandantenfähigkeit) und darauf aufbauend Spec 1a (Mini-Portal) vollständig durchspielen lassen — **inklusive** dem Nachweis, dass zwei Mandanten sauber voneinander isoliert sind, bevor irgendetwas in Richtung Produktion geht.

---

## 2. Lokale Subdomains ohne Hosts-Datei

`*.localhost` wird von allen gängigen Browsern automatisch auf `127.0.0.1` aufgelöst (RFC 6761) — kein Eintrag in der Windows-`hosts`-Datei, keine Admin-Rechte nötig.

In den lokalen Settings (Dev-`.env` bzw. `settings/local.py`, wie Dev/Prod bereits getrennt sind):

```python
ALLOWED_HOSTS = ['.localhost', '127.0.0.1', 'localhost']
```

Domain-Werte sind bewusst je Umgebung unterschiedlich: lokal `demme.localhost`, produktiv später die echte Subdomain. Kein Widerspruch zu Spec 0/1a, sondern normale Trennung von Dev- und Prod-Konfiguration.

---

## 3. Tenants lokal anlegen

Bestehende lokale PostgreSQL-16-Instanz reicht aus, kein separater Server nötig.

```powershell
# Shared-Schema (public) migrieren
python manage.py migrate_schemas --shared

# Ersten Mandanten anlegen
python manage.py create_tenant --schema=demme `
    --name="Demme Immobilien Verwaltung GmbH" `
    --domain=demme.localhost

# Zweiten Test-Mandanten SOFORT mit anlegen, nicht erst am Ende
python manage.py create_tenant --schema=testweg `
    --name="Test-Hausverwaltung GmbH" `
    --domain=testweg.localhost
```

Der zweite Mandant ist kein „nice to have" — er ist die einzige Möglichkeit, die Kernanforderung aus Spec 0 (Datenisolation) lokal überhaupt zu prüfen, bevor der erste echte externe Mandant hinzukommt.

---

## 4. Magic-Link-Mails lokal sichtbar machen

Kein echter Mailversand beim Testen. Zwei Optionen, `immo-builder` wählt anhand des Testbedarfs:

**Schnell (Standard für diese Phase):**
```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```
Der Magic Link erscheint im Terminal-Log, zum Copy-Paste in den Browser.

**Realistischer (optional, wenn Mail-Layout/Betreff mitgeprüft werden soll):**
[Mailpit](https://github.com/axllent/mailpit) als lokaler SMTP-Catcher mit Weboberfläche unter `localhost:8025`. Nicht das produktive Microsoft-Graph-Postfach für lokale Tests verwenden.

---

## 5. Frontend lokal

- React-Dev-Server auf eigenem Port, API-Calls gegen `http://demme.localhost:8000/api/v1/portal/`
- CORS lokal großzügig für `*.localhost` konfigurieren — **nicht** die Produktions-CORS-Settings für lokale Tests übernehmen, sonst blockt der Browser die Cross-Subdomain-Requests zwischen Frontend- und API-Port

```python
# Nur in lokalen Settings, nie in Produktion:
CORS_ALLOWED_ORIGIN_REGEXES = [r"^http://[\w-]+\.localhost:\d+$"]
```

---

## 6. Testreihenfolge

1. **Spec 0 lokal vollständig durchspielen**, inkl. Verifikation Kap. 6 unten
2. Erst danach **Spec 1a (Mini-Portal)** gegen `demme.localhost` testen
3. Kritischer Test für Spec 1a: Einladung + Magic-Link-Login unter `demme.localhost` UND `testweg.localhost` parallel — Eigentümer aus `demme` darf unter `testweg` nicht einloggbar sein und umgekehrt

---

## 7. Verifikation (immo-explorer, read-only)

- [ ] `demme.localhost:8000/admin/` zeigt Demme-Daten, `testweg.localhost:8000/admin/` zeigt eine leere/eigene Instanz — keine Vermischung
- [ ] Ein in `demme` angelegter Testdatensatz (z.B. Testobjekt) ist unter `testweg` nicht sichtbar, auch nicht über direkte ID-Abfrage in der API
- [ ] Magic-Link-Login funktioniert unter beiden Subdomains unabhängig voneinander
- [ ] Bestehende Testsuite (718 Tests) läuft gegen das Schema `demme` unverändert grün
- [ ] Konsolen-E-Mail-Backend zeigt den Magic-Link-Token korrekt lesbar im Terminal an

Erst wenn alle Punkte grün sind, gilt Spec 0 als lokal verifiziert und Spec 1a kann aufgesetzt werden.
