# Bestandsaufnahme Eigentümer-Portal

**Stand:** 2026-09-09 · **Basis:** Branch `main`, HEAD `1cbceae` · **Art:** reine Ist-Aufnahme, keine Code-Änderung
**Bezug:** `aktuelle Umsetzung/CLAUDE_CODE_ANLEITUNG_WEG_PORTAL_MINI_v1_0.md` (Spec 1a), `docs/CLAUDE_CODE_ANLEITUNG_PORTAL_LAYOUT_UPDATE_v1_0.md`, Mockup `docs/immocore_portal_mockup.html`

---

## 1. Abgrenzung: was „Portal" im Code bedeutet

Das Portal ist eine **eigene Anwendung im gleichen Projekt**, kein Menüpunkt der Verwaltungsoberfläche — getrennt in vier Dimensionen:

| Dimension | Portal | Interner Bereich |
|---|---|---|
| Backend-App | `apps.portal` (`backend/apps/portal/apps.py` → `PortalConfig`, verbose_name „Eigentümer-Portal") | übrige `apps.*` |
| Authentifizierung | `PortalSessionAuthentication`, Header `Authorization: Portal <token>` (`backend/apps/portal/auth.py`) | SimpleJWT, `Bearer` |
| Identität | `PortalZugang` an `Person`, **kein** `django.contrib.auth.User`; DRF erhält den Ersatz-User `PortalNutzer` (ohne `has_perm`/`groups`) | `auth.User` + `Mitarbeiter` |
| Frontend | `frontend/src/pages/portal/*`, eigener axios-Client und eigener Token-Key `portal_token` (`frontend/src/api/portal.ts`) | `Layout` / `ProtectedRoute`, Token des internen Clients |

Zusätzlich existiert eine **zweite, davon unabhängige Außenfläche**: die tokenbasierte Handwerker-Auftragsbestätigung (`frontend/src/pages/oeffentlich/AuftragBestaetigung.tsx`, Route `/auftrag-bestaetigung/:token`, `frontend/src/App.tsx:87`). Sie gehört nicht zu `apps.portal` und kennt keine Sitzung.

---

## 2. Backend-Ist

### 2.1 Datenmodell — `backend/apps/portal/models.py`

| Klasse | Zweck | Belege / Kennwerte |
|---|---|---|
| `PortalZugang` | Berechtigung je Person (OneToOne → `apps.personen.models.Person`), `aktiv`, `eingeladen_von`, `erstaktivierung_am`, `letzter_login`, `email_pending`; abgeleiteter `status` = `eingeladen` / `aktiv` / `gesperrt` | `@property status` in `models.py` |
| `PortalToken` | Ein Modell für drei Einmal-Links über `typ`: `einladung`, `magic`, `email_bestaetigung`; `ziel_email` friert die zu bestätigende Adresse ein | Gültigkeiten zentral als Modul-Konstanten: `EINLADUNG_GUELTIG_STUNDEN=72`, `MAGIC_LINK_GUELTIG_MINUTEN=15`, `EMAIL_BESTAETIGUNG_GUELTIG_STUNDEN=24` |
| `PortalSession` | Opakes Zufalls-Token (`secrets.token_urlsafe(48)`), `SESSION_GUELTIG_STUNDEN=12`; DB-Datensatz, damit Sperren sofort wirkt | `auth.py`: Prüfung `if not session.zugang.aktiv`, Zugriffszeit nur alle 5 min geschrieben (`_ZUGRIFF_SCHREIBINTERVALL`) |
| `PersonStammdatenAenderung` | GoBD-Audit, **ein Eintrag je geändertem Feld**, `quelle='Portal-Selbständerung'`, `on_delete=PROTECT` auf `person` | geschrieben in `stammdaten_service.protokolliere()` |

Migrationen: `0001_initial.py`, `0002_erstaktivierung_nachziehen.py`.

### 2.2 Endpunkte — `backend/apps/portal/urls.py` (eingehängt in `backend/config/urls.py:139`)

Portal-Sitzung (`IstPortalNutzer`, Views in `backend/apps/portal/views.py`):

- `POST /api/v1/portal/auth/magic-link/request/` → `MagicLinkAnfordernView` — anonym, **immer neutrale Antwort** (`_NEUTRALE_ANTWORT`, Enumeration-Schutz), Throttle-Scope `portal_auth` = `60/hour` (`backend/config/settings.py:137`)
- `POST .../auth/magic-link/verify/` → `MagicLinkEinloesenView` (löst Einladung *und* Magic Link ein) · `POST .../auth/logout/` → `AbmeldenView`
- `GET /api/v1/portal/meine-einheiten/` → `MeineEinheitenView`
- `GET|PATCH /api/v1/portal/meine-daten/` → `MeineDatenView` (Adresse, Telefon)
- `PATCH .../meine-daten/bankverbindung/` → `BankverbindungView` · `POST .../meine-daten/email/` → `EmailAendernView` · `POST .../meine-daten/email/bestaetigen/` → `EmailBestaetigenView` (anonym, weil der Link meist im neuen Postfach geöffnet wird)
- `GET /api/v1/portal/iban-check/` → `IbanPruefenView`

Intern (Mitarbeiter-JWT, `IsAuthenticated`, `backend/apps/portal/views_verwaltung.py`): `PortalZugangViewSet` als `ReadOnlyModelViewSet` unter `/api/v1/portal-verwaltung/zugaenge/` mit den Aktionen `einladen` (`@action(detail=False)`), `sperren`, `entsperren`. Bewusst **nicht** unter `/portal/`, damit ein Portal-Token hier nichts erreicht. Einladbar ist nur `person_typ '100'` (`PERSON_TYP_EIGENTUEMER`). **Selbstregistrierung ist nicht vorgesehen** — ein Zugang entsteht ausschließlich hier.

### 2.3 Services — `backend/apps/portal/services/`

| Datei | Kernfunktionen |
|---|---|
| `zugang_service.py` | `lade_ein()`, `erzeuge_magic_link()`, `erzeuge_email_bestaetigung()`, `loese_token_ein()`, `pruefe_rate_limit()`, `finde_zugang_per_email()`, `person_email()`, `_entwerte_offene_token()`; Fehlerklassen `PortalFehler`, `TokenUngueltig`, `ZugangGesperrt`, `RateLimitErreicht` |
| `stammdaten_service.py` | `aktualisiere_kontakt()`, `aktualisiere_bankverbindung()` (zieht ein aktives `SEPAMandat` mit), `stosse_email_aenderung_an()`, `bestaetige_email()`, `protokolliere()`; `StammdatenFehler` |
| `einheiten_service.py` | `meine_einheiten()` liefert die WEG-Karten mit ihren Einheiten; MEA kommt aus `VerteilerschluesselWert` (`vs_typ='mea'`) über `_mea_werte()` |
| `mail_service.py` | `versende_einladung()`, `versende_magic_link()`, `versende_email_bestaetigung()`; `versand_konfiguriert()` / `VersandNichtKonfiguriert` verhindern stillen Verlust über das Konsolen-Backend; Links aus `settings.FRONTEND_BASE_URL` (`backend/config/settings.py:188`) |

Mailvorlagen: `backend/templates/email/portal_einladung.{html,txt}`, `portal_magic_link.{html,txt}`, `portal_email_bestaetigung.{html,txt}`.

### 2.4 Tests — `backend/apps/portal/tests/` (81 Tests, gemeinsame Fixtures in `basis.py`)

`test_auth.py` (20) · `test_stammdaten.py` (29) · `test_einheiten_und_isolation.py` (12, u. a. Fremdzugriff/Isolation) · `test_iban_pruefung.py` (11) · `test_verwaltung.py` (9).

---

## 3. Frontend-Ist

Routen in `frontend/src/App.tsx:92-99` — eigener Zweig **vor** den internen Routen, damit der Catch-all der Layout-Route ihn nicht verschluckt:

| Route | Komponente | Datei |
|---|---|---|
| `/portal/login` | `PortalLogin` | `frontend/src/pages/portal/PortalLogin.tsx` |
| `/portal/anmelden/:token` | `PortalAnmelden` | `frontend/src/pages/portal/PortalAnmelden.tsx` |
| `/portal/email-bestaetigen/:token` | `PortalEmailBestaetigen` | `frontend/src/pages/portal/PortalEmailBestaetigen.tsx` |
| `/portal` (Rahmen, Index-Redirect auf `einheiten`) | `PortalLayout` | `frontend/src/pages/portal/PortalLayout.tsx` |
| `/portal/einheiten` | `MeineEinheiten` | `frontend/src/pages/portal/MeineEinheiten.tsx` |
| `/portal/daten` | `MeineDaten` | `frontend/src/pages/portal/MeineDaten.tsx` |

- **API-Schicht:** `frontend/src/api/portal.ts` — eigener `portalClient` (`baseURL: '/api/v1/portal'`), Request-Interceptor setzt `Authorization: Portal …`, bei 401 `clearPortalToken()` und Sprung auf `/portal/login`; **kein** stiller Token-Refresh. Am Dateiende die internen Verwaltungsaufrufe (`portalZugaengeLaden`, `portalEinladen`, `portalZugangSperren`, `portalZugangEntsperren`) — die laufen über den internen Client, nicht über `portalClient`.
- **Layout-Update ist umgesetzt** (Merge `db5efb3`, Branch `feature/portal-layout-buttons`): `MeineEinheiten.tsx` rendert WEG-Buttons → Einheiten-Buttons → Reiter `ReiterId = 'konto' | 'dokumente' | 'vorgaenge'`; jeder WEG- oder Einheiten-Wechsel springt auf `konto` zurück (`setReiter('konto')`, Zeilen 135 und 140).
- **Optik:** eigene Tailwind-Palette `portal.*` (`ink`, `soft`, `paper`, `line`, `brand`, `brand-soft`, `accent`, `debit`, `credit`) in `frontend/tailwind.config.js:20-30`, bewusst getrennt von `primary`.
- **Selbstpflege:** `MeineDaten.tsx` mit `KontaktSektion`, `BankverbindungSektion` (IBAN-Prüfung über `frontend/src/components/ui/IbanInput.tsx`) und `EmailSektion` (Zwei-Schritt-Bestätigung über `email_pending`).
- **Intern:** `frontend/src/pages/personen/PortalZugangKarte.tsx` auf `PersonDetail` — Status-Badge (`eingeladen` / `aktiv` / `gesperrt`) plus Einladen/Sperren/Entsperren.

---

## 4. Lücken und offene Punkte

1. **Die drei Reiter haben keinen Inhalt.** `MeineEinheiten.tsx` zeigt in `konto`, `dokumente` und `vorgaenge` nur `Platzhalter`-Texte, die Kennzahlkarten stehen fest auf „wird in Kürze angezeigt" / „Personenkonto in Vorbereitung" (Zeilen 205-217 und 238-245). Es existiert **kein** Portal-Endpunkt für Saldo, Buchungsverlauf, Dokumente oder Vorgänge.
2. **Spec 1b liegt nicht im Repo.** `docs/CLAUDE_CODE_ANLEITUNG_PORTAL_LAYOUT_UPDATE_v1_0.md` verweist auf `CLAUDE_CODE_ANLEITUNG_WEG_PORTAL_KONTO_v1_0.md` (Spec 1b, Konto-Reiter); diese Datei ist im Projektbaum nicht vorhanden.
3. **Vorgänge sind vorbereitet, aber nicht angebunden.** `apps.vorgaenge` hat `Vorgang.portal_sichtbar` (`backend/apps/vorgaenge/models.py:138`), `vorgang_service.setze_portal_sichtbar()` und `vorgang_service.portal_ansicht()` sowie den internen Endpunkt `portal_sichtbar_setzen` (`backend/apps/vorgaenge/views.py:135`). Es fehlt die lesende Route unter `/api/v1/portal/`, die `portal_ansicht()` an den Eigentümer ausliefert. `VorgangEreignis.intern` steht mit `default=True` auf der sicheren Seite.
4. **Betriebsvoraussetzungen auf Live.** Ohne SMTP (`EMAIL_HOST`) wirft `mail_service._pruefe_versandfaehig()` in Produktion `VersandNichtKonfiguriert` — dann geht **keine** Einladung und kein Magic Link raus. Fehlt `FRONTEND_BASE_URL`, fällt der Default `http://localhost:3000` und damit ein unbrauchbarer Link in die Mail (`backend/config/settings.py:188`).
5. **Mandantenfähigkeit (Spec 0) fehlt weiterhin** — festgehalten als Abweichung 008 in `docs/PROJEKT_STATUS.md:297`; das Portal läuft im bestehenden Single-Schema. Ebenfalls dort dokumentiert: Autorisierung über `request.portal_zugang.person` statt `request.user.person`, `kontoinhaber` nicht bearbeitbar, MEA aus `VerteilerschluesselWert`.
6. **Publikum eingeschränkt.** Nur `person_typ '100'` (Eigentümer) erhält Zugang; Mieter und Kreditoren sind in dieser Ausbaustufe kein Portal-Publikum (`views_verwaltung.py`).

---

## 4a. Nachtrag 2026-09-09 — was seit dieser Aufnahme geschlossen wurde

Die Aufnahme oben bleibt als Phase-0-Stand stehen (HEAD `1cbceae`). Umgesetzt wurde daraufhin die Spec
`CLAUDE_CODE_ANLEITUNG_PORTAL_VORGAENGE_SALDO_FAELLIGKEITEN_v1_1.md` (lokal, nicht committet):

- Punkt 1 **teilweise geschlossen** — Konto- und Vorgänge-Reiter haben echte Daten (`KontoReiter.tsx`, `VorgaengeReiter.tsx`); der Dokumente-Reiter bleibt bewusst Platzhalter.
- Punkt 2 **gegenstandslos** — diese Spec übernimmt inhaltlich die Rolle der fehlenden Spec 1b für den Konto-Reiter.
- Punkt 3 **geschlossen** — `GET/POST /api/v1/portal/vorgaenge/` und `GET /api/v1/portal/vorgaenge/<id>/` (`apps/portal/views_vorgaenge.py`), Scoping über `vorgang_service.portal_sichtbare_vorgaenge`.
- Punkte 4, 5, 6 **unverändert offen** (SMTP/`FRONTEND_BASE_URL`, Mandantenfähigkeit, nur `person_typ '100'`).

---

## 5. Verifikation dieser Aufnahme

Alle Aussagen sind gegen den Arbeitsbaum auf `main` (`1cbceae`) gelesen. Im `git status` zum Zeitpunkt der Aufnahme war **keine** Portal-Datei geändert — die Aufnahme beschreibt damit den committeten Stand, nicht lokale Zwischenarbeit.
