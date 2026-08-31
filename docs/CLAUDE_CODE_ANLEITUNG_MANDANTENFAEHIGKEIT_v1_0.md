# CLAUDE CODE — IMMOCORE
## Mandantenfähigkeit (django-tenants Einführung) — Spec 0

**Version:** 1.0
**Stand:** August 2026
**Status:** 🟡 Bereit zur Umsetzung — Fundament für WEG-Portal (Spec 1, folgt separat)
**Bezug:** `IMMOCORE_PROJEKTSTAND_AKTUELL.md` (Git-HEAD `3fb630d`, 87 Modelle, 12 Apps, 180 Migrationen, Single-Schema), IMMOCORE_Ausgangsspezifikation v1.1

---

## 0. Orchestrierung

**Orchestrator: Opus.**
Verantwortlich für Gesamtplanung, die Shared/Tenant-Zuordnung strittiger Modelle (Kap. 3), Freigabe jedes Phasenübergangs (HALT-Gates, Kap. 6) und Eskalationsinstanz bei Architektur-Konflikten. Der Orchestrator delegiert jede Phase an die kleinstmögliche ausreichende Modellstufe und startet, wo die Phasen unabhängig sind, mehrere Sub-Agenten parallel.

**Sub-Agenten:**

| Agent | Modell | Aufgabe |
|---|---|---|
| `immo-explorer` | Haiku | Read-only Bestandsaufnahme vor jedem Umbauschritt: Datensatz-Zählung je Tabelle, FK-Beziehungen über App-Grenzen hinweg, Verifikation nach jeder Phase gegen die Referenzwerte aus Phase 0 |
| `immo-builder` | Sonnet | Implementierung: django-tenants-Einbindung, Settings-Umbau, Migrationen, Management-Commands, Middleware |
| `immo-architect` | Opus | Eskalation bei unklarer Shared/Tenant-Zuordnung einzelner Modelle, FK-Konflikte zwischen Shared und Tenant Apps |

**Parallelisierung:** Phase 0 (Bestandsaufnahme) läuft vollständig durch `immo-explorer`, bevor `immo-builder` beginnt — hier keine Parallelität, da alle Folgephasen auf den Referenzwerten aufbauen. Ab Phase 2 können zwei `immo-builder`-Instanzen parallel an unabhängigen App-Gruppen arbeiten (z.B. `buchhaltung`+`konten` parallel zu `personen`+`rechnungen`), sofern die Reihenfolge aus Kap. 3.2 (FK-Abhängigkeiten) eingehalten wird. `immo-explorer` verifiziert kontinuierlich im Hintergrund, während `immo-builder` die nächste Teilaufgabe bereits beginnt.

---

## 1. Zweck und Abgrenzung

### 1.1 Ziel dieser Spec

Umbau von IMMOCORE von einem Single-Tenant-System auf **Schema-per-Tenant Multi-Tenancy** mittels `django-tenants`. Demme Immobilien Verwaltung GmbH wird dabei zum **ersten von potenziell vielen Mandanten** — technisch gleichberechtigt, kein Sonderstatus.

### 1.2 Explizit NICHT Teil dieser Spec

| Thema | Status |
|---|---|
| Portal-Features (Subdomain-Login-UI, Branding-Rendering, Magic-Link-Auth, Personenkonto-/Dokumente-Endpoints) | Folgt als **Spec 1 „WEG-Portal"**, baut auf dieser Spec auf |
| Celery-Beat-Hintergrundjobs (Mail-Intake, camt-Import, Mahnlauf etc.) | Bleiben **global**, laufen unverändert nur für Demme; Tenant-Awareness wird beim Onboarding des 2. Mandanten in einer eigenen Spec nachgezogen |
| Datei-Ablage STRATO HiDrive S3 | Bleibt **global**, Mandanten-Trennung (Prefix/Bucket) folgt separat |
| Self-Service-Onboarding | Vorerst **manuelles Management-Command** (Kap. 7); UI-Workflow ist eine spätere Ausbaustufe |

Diese bewusste Abgrenzung hält den Blast-Radius dieser Spec auf reine Infrastruktur begrenzt — keine fachliche Logik ändert sich, nur die Datenhaltung.

---

## 2. Grundprinzip

Mit `django-tenants` bekommt jeder Mandant ein **eigenes PostgreSQL-Schema**. Zwei App-Kategorien:

- **`SHARED_APPS`**: Tabellen leben im `public`-Schema, für alle Mandanten gemeinsam sichtbar
- **`TENANT_APPS`**: Tabellen werden **je Mandant-Schema** dupliziert — vollständig isolierte Daten

---

## 3. Shared vs. Tenant — Klassifizierung

### 3.1 Entscheidungsgrundlage aus den Klärungsfragen

- Demme ist **nur ein Mandant unter vielen**, Mitarbeiterzugriff strikt pro Mandant getrennt → **kein** mandantenübergreifender Superadmin-Zugang in dieser Spec
- Stammdaten-Vorlagen (Musterkontenrahmen, `VorgangTyp`, `Abrechnungsart`) → **je Mandant eigene, unabhängig anpassbare Kopie**, nicht geteilt

Daraus folgt: praktisch **alle 12 fachlichen Apps werden `TENANT_APPS`**, inklusive Benutzer- und Session-Verwaltung (jeder Mandant hat eigene Mitarbeiter-Accounts, keine geteilten Logins).

### 3.2 Klassifizierungstabelle

| App / Komponente | Einordnung | Anmerkung |
|---|---|---|
| `django_tenants` (Kern-Package) | — | liefert Middleware/Router, kein eigenes Datenschema |
| Neue App `mandanten` (`Mandant`, `Domain`) | **SHARED_APPS** | muss zwingend im `public`-Schema liegen — hier wird aufgelöst, welches Schema pro Request zuständig ist |
| `django.contrib.contenttypes` | **SHARED_APPS** | Vorgabe von django-tenants |
| `django.contrib.staticfiles` | **SHARED_APPS** | keine mandantenspezifischen Daten |
| `django.contrib.auth`, `django.contrib.admin`, `django.contrib.sessions` | **TENANT_APPS** | Mitarbeiterzugriff strikt pro Mandant getrennt (Klärung Kap. 0) |
| `abrechnung_wp`, `buchhaltung`, `dokumente`, `handwerker`, `konten`, `massenimport`, `mitarbeiter`, `objekte`, `personen`, `prozesse`, `rechnungen`, `vorgaenge` | **TENANT_APPS** | alle 12 Projekt-Apps vollständig, inkl. Stammdaten-Modelle (`Konto`/Musterkontenrahmen, `VorgangTyp`, `Abrechnungsart`) — je Mandant eigene Kopie gemäß Klärung |

**Escalation-Regel für `immo-architect`:** Sollte beim Durchgehen der 87 Modelle ein Fall auftauchen, der nicht eindeutig in obige Tabelle passt (z.B. ein zukünftiges plattformweites Reporting-Modell), wird das **nicht** von `immo-builder` autonom entschieden, sondern an `immo-architect` eskaliert und Patrik zur Bestätigung vorgelegt.

---

## 4. Neue Modelle

### 4.1 `Mandant` (TenantMixin, SHARED_APPS → App `mandanten`)

| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | UUIDField (PK) | |
| `schema_name` | CharField(63) | von `django-tenants` vorgegeben, z.B. `demme` |
| `name` | CharField(200) | Anzeigename, z.B. „Demme Immobilien Verwaltung GmbH" |
| `aktiv` | BooleanField, default `True` | pausierte Mandanten bleiben technisch bestehen, aber ohne Zugriff |
| `erstellt_am` | DateTimeField, auto_now_add | |

### 4.2 `Domain` (DomainMixin, SHARED_APPS → App `mandanten`)

| Feld | Typ | Anmerkung |
|---|---|---|
| `domain` | CharField | z.B. `demme.weg-portal.de` |
| `mandant` | FK → `Mandant` | |
| `is_primary` | BooleanField | eine Primär-Domain je Mandant Pflicht |

---

## 5. Settings-Umbau (Auszug für `immo-builder`)

```python
INSTALLED_APPS = []  # entfällt zugunsten des Splits

SHARED_APPS = (
    'django_tenants',
    'apps.mandanten',            # neu
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
)

TENANT_APPS = (
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'apps.abrechnung_wp',
    'apps.buchhaltung',
    'apps.dokumente',
    'apps.handwerker',
    'apps.konten',
    'apps.massenimport',
    'apps.mitarbeiter',
    'apps.objekte',
    'apps.personen',
    'apps.prozesse',
    'apps.rechnungen',
    'apps.vorgaenge',
)

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        # ... bestehende Zugangsdaten unverändert
    }
}

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
] + MIDDLEWARE  # ganz oben einfügen

TENANT_MODEL = "mandanten.Mandant"
TENANT_DOMAIN_MODEL = "mandanten.Domain"
```

`immo-builder` prüft dabei explizit, ob aktuell verwendete Middleware (JWT-Auth, CORS) mit `TenantMainMiddleware` an erster Stelle kollisionsfrei zusammenarbeitet — camt-Import- und Rechnungspipeline-Middleware (sofern vorhanden) danach einreihen.

---

## 6. Migrationsstrategie — Phasenplan mit HALT-Gates

Downtime-Budget: **kurzes nächtliches Wartungsfenster (15–60 Min.) bestätigt** (Klärung Kap. 0). GoBD-Grundsatz bleibt during der Migration verbindlich: keine Buchungsdaten dürfen verloren gehen oder sich inhaltlich verändern.

### Phase 0 — Bestandsaufnahme (immo-explorer, read-only)

- Vollständige Datensatz-Zählung je Tabelle als Referenzwert
- Kontrollsummen der buchhaltungsrelevanten Tabellen (`Buchung`, `HausgeldSollstellung`, `OffenerPosten`) — Summe `betrag` je Tabelle als GoBD-Referenz
- Vollständiger `pg_dump` der Produktiv-DB (unabhängig vom späteren Schema-Umbau, als Rollback-Sicherung)
- **Kein Code-Änderung in dieser Phase.**

**HALT:** Ergebnis der Bestandsaufnahme geht an Patrik zur Bestätigung, bevor Phase 1 beginnt.

### Phase 1 — Grundgerüst (immo-builder, auf Sandbox/Dev getestet, NICHT live)

- `django-tenants` Paket einbinden, Settings gemäß Kap. 5 umbauen
- Neue App `mandanten` mit `Mandant`/`Domain`-Modellen anlegen
- Migrationen erzeugen und **ausschließlich in der Sandbox-Umgebung** (Kap. „Sandbox year-run", eigene DB Port 8010) durchspielen
- `immo-explorer` verifiziert: Sandbox-Migration bricht bestehende Tests (718 Tests) nicht

### Phase 2 — Public-Schema live einrichten

- `public`-Schema-Migrationen (`SHARED_APPS`) auf Produktion ausführen — **unkritisch, keine Downtime nötig**, da `public` bisher leer bzgl. Fachdaten ist
- Ersten Mandanten-Datensatz `demme` **noch nicht** anlegen (das geschieht in Phase 3 im Wartungsfenster, um Datenstand exakt zu kontrollieren)

### Phase 3 — Wartungsfenster (kritische Phase)

1. Produktivsystem in Wartungsmodus (Nginx-Wartungsseite)
2. `create_tenant`-Command (Kap. 7) legt Schema `demme` an
3. Bestehende Fachdaten aus dem alten `public`-Schema in das neue Schema `demme` umziehen (`pg_dump`/`pg_restore` mit Schema-Remapping, oder `ALTER TABLE ... SET SCHEMA` je Tabelle — `immo-builder` wählt die für PostgreSQL 16 robustere Variante und dokumentiert die Wahl)
4. `TENANT_APPS`-Migrationen im neuen Schema `demme` ausführen
5. Middleware/Domain-Eintrag `demme` → bestehende Live-Domain (bis Spec 1 die künftige Subdomain einführt) verknüpfen
6. Restart, Wartungsmodus beenden

### Phase 4 — Verifikation (immo-explorer)

- Datensatz-Zählung je Tabelle im neuen Schema gegen Referenzwerte aus Phase 0 — **exakte Übereinstimmung erforderlich**
- Kontrollsummen-Abgleich der buchhaltungsrelevanten Tabellen (GoBD-kritisch, keine Toleranz)
- Smoke-Test: Login, Objektliste, eine Buchung anlegen, Testsuite (718 Tests) gegen das neue Schema laufen lassen

**HALT:** Nur bei 100%-Übereinstimmung aller Referenzwerte geht es weiter. Bei jeder Abweichung — Rollback auf den `pg_dump` aus Phase 0, keine Bagatellisierung von Differenzen.

### Phase 5 — Altbestand archivieren (kein Löschen)

- Altes `public`-Schema-Fachdaten werden **umbenannt** (z.B. Schema-Suffix `_archiv_pre_tenant`), **nicht gelöscht**
- Aufbewahrungsfrist: mindestens 14 Tage Produktionsbeobachtung

**HALT (hart, manuelle Freigabe Patrik zwingend erforderlich):** Endgültiges Löschen des archivierten Altbestands erfolgt **ausschließlich** nach expliziter Freigabe nach Ablauf der Beobachtungsfrist — nie automatisiert, nie durch einen Agenten selbständig ausgelöst.

---

## 7. Management Commands

```bash
# Neuen Mandanten anlegen (manuell, Selfservice-UI ist spätere Ausbaustufe)
python manage.py create_tenant --schema=demme \
    --name="Demme Immobilien Verwaltung GmbH" \
    --domain=<bestehende-live-domain>

# Stammdaten-Vorlagen in neuen Mandanten einspielen (Musterkontenrahmen, VorgangTyp, Abrechnungsarten)
python manage.py seed_mandant_stammdaten --schema=demme
```

`seed_mandant_stammdaten` lädt die Stammdaten-Vorlagen aus **Fixture-Dateien** (nicht aus einem anderen Mandanten-Schema — Schema-Isolation in PostgreSQL verbietet das ohnehin, und Fixtures halten die Vorlage versionierbar und unabhängig von Live-Daten eines bestehenden Mandanten). Jeder Mandant erhält danach eine eigene, unabhängig veränderbare Kopie — Änderungen eines Mandanten wirken sich nie auf einen anderen aus.

Standard-`django-tenants`-Befehl `migrate_schemas` bleibt für laufenden Betrieb (Migrationen künftig auf alle oder einzelne Schemas anwenden) unverändert nutzbar.

---

## 8. Was diese Spec bewusst offen lässt (Verweis auf Folge-Specs)

| Thema | Wann |
|---|---|
| Spec 1 „WEG-Portal": Subdomain-Login-UI, Magic-Link-Auth, Branding je Mandant, Portal-Endpoints (Personenkonto/Dokumente/Vorgänge) | Direkt im Anschluss an diese Spec |
| Celery-Beat Tenant-Awareness (Mail-Intake, camt-Import, Mahnlauf) | Beim Onboarding des 2. echten Mandanten |
| S3-Storage-Trennung (Prefix/Bucket je Mandant) | Separate Spec, unabhängig vom Zeitpunkt |
| Self-Service-Onboarding-Workflow (UI statt Management-Command) | Spätere Ausbaustufe, kein aktueller Bedarf bei 1–2 Mandanten |

---

## 9. Akzeptanzkriterien

- [ ] Alle 718 bestehenden Tests laufen nach dem Umbau unverändert grün, ausgeführt **innerhalb** des Schemas `demme`
- [ ] Datensatz-Zählung je Tabelle stimmt zwischen Referenzwert (Phase 0) und neuem Schema exakt überein
- [ ] Kontrollsummen aller buchhaltungsrelevanten Tabellen stimmen exakt überein (keine Toleranz)
- [ ] Login, Objektliste, Buchungsanlage funktionieren im Live-Betrieb nach der Migration ohne Funktionsverlust
- [ ] Alter `public`-Schema-Fachbestand ist archiviert, nicht gelöscht
- [ ] `create_tenant` und `seed_mandant_stammdaten` legen einen zweiten Test-Mandanten in der Sandbox erfolgreich und vollständig isoliert an (Nachweis: Testdaten des zweiten Mandanten sind aus dem `demme`-Schema heraus nicht sichtbar)
