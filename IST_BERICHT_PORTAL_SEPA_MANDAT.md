# Ist-Bericht Phase 0 — Portal: SEPA-Lastschriftmandat (V1–V5)

Erhoben 2026-11-03 durch `immo-explorer` (4 parallele Aufträge), stichprobenartig
vom Orchestrator gegengelesen. Alle Pfade relativ zu Repo-Root. Spec:
`docs/CLAUDE_CODE_ANLEITUNG_PORTAL_SEPA_MANDAT_v1_0.md`.

## V1 — Feldlisten (exakt)

### `SEPAMandat` — `backend/apps/personen/models.py:11-38`
| Feld | Typ / Constraints |
|---|---|
| id | UUID pk |
| mandatsreferenz | CharField(35), **unique** |
| iban | CharField(34), Pflicht |
| bic | CharField(11), blank |
| unterzeichnet_am | DateField, Pflicht |
| aktiv | BooleanField, default True |
| sequence_type | CharField(4), choices RCUR/FRST, default 'RCUR', blank |

Meta: ordering `['-unterzeichnet_am']`. Keine Constraints. Nur `__str__`.
**Kein** gueltig_bis / widerrufen_am / FK auf Person, Einheit oder EV.
Person-Bezug nur rückwärts über `Person.sepa_mandat`.

### `Person` (Mandats-/Bankfelder) — `backend/apps/personen/models.py`
| Feld | Typ | Zeile |
|---|---|---|
| ibans | JSONField(default=list) | :122 |
| sepa_mandat | FK(SEPAMandat, SET_NULL, null, blank, **related_name='personen'**) | :125-128 |

FK ist many-to-one: mehrere Personen *können* dasselbe Mandat referenzieren
(Dev-DB: 0 Fälle). Kein BIC-Feld auf Person.

### `EigentumsVerhaeltnis` — `backend/apps/personen/models.py:311-370`
| Feld | Typ |
|---|---|
| id | UUID pk |
| einheit | FK(Einheit, CASCADE, related_name='eigentumsverhaeltnisse') |
| person | FK(Person, PROTECT, related_name='eigentumsverhaeltnisse') |
| beginn | DateField |
| ende | DateField null/blank ("Null = aktuell aktiv") |

UniqueConstraint `uniq_aktiver_vertrag_je_einheit` (einheit, ende IS NULL) →
max. **ein offenes EV je Einheit**. Property `ist_aktiv` = `ende is None` (:370).
Kein Manager/QuerySet `aktiv()`.

### `PersonStammdatenAenderung` — `backend/apps/portal/models.py:183-215` (App **portal**)
person FK PROTECT (related 'stammdaten_aenderungen'), feld Char50, alter_wert /
neuer_wert Text, quelle Char50 default `QUELLE_PORTAL='Portal-Selbständerung'`,
zeitstempel auto_now_add. Index (person, feld).

### `Einheit` / `Objekt` — `backend/apps/objekte/models.py`
Einheit (:138): objekt FK (related 'einheiten'), einheit_nr Char20, einheit_typ,
lage Char255. **Kein** bezeichnung-, weg- oder MEA-Feld. Objekt (:5): objektnummer,
objekt_typ (WEG/ZH/SEV), bezeichnung, strasse, plz, ort. Kein eigenes WEG-Modell.

## V2 — Lesestellen `Person.sepa_mandat` (Produktivcode)

| Stelle | Was |
|---|---|
| `buchhaltung/services/auto_pipeline_service.py:158-199` `_filtere_lastschrift_kandidaten` | **Vorfilter des Einzugs**: `if not person.sepa_mandat` → `kein_sepa_mandat`; `sequence_type != 'RCUR'` → `mandat_typ_frst`; leere IBAN → `keine_iban`. **Prüft `aktiv` NICHT.** |
| `buchhaltung/services/sepa_lastschrift.py:216-238` `commite_lastschriftlauf` | `mandat = person.sepa_mandat` (:220); Zugriffe `.iban/.bic/.mandatsreferenz/.unterzeichnet_am` (:232-235). Kein None-Check. Einziger Produktiv-Aufrufer: auto_pipeline_service.py:108. |
| `buchhaltung/views.py:1483, 1510-1517` | View-Filter mit `getattr(person,'sepa_mandat',None)` + `.aktiv`-Check → `ohne_mandat`. |
| `portal/services/stammdaten_service.py:146-150` `aktives_mandat(person)` | liest `person.sepa_mandat`, prüft aktiv. |
| `portal/services/stammdaten_service.py:166-245` `aktualisiere_bankverbindung(zugang, daten)` | ändert IBAN/BIC in-place, mandatsreferenz nie; `Person.ibans` neue an Pos. 0 (:203-211); Audit 'iban' + 'sepa_mandat'. |
| `personen/views.py:67, 391-396` | select_related; `SEPAMandatViewSet` (ModelViewSet, IsAuthenticated). |
| `personen/serializers.py:5-21` | SEPAMandatSerializer / PersonSerializer `fields='__all__'`. |
| `personen/admin.py:18-19` | SEPAMandatAdmin. |
| `konten/views.py:246-256, 267, 296, 320` | `_sepa_mandat_data()` im Personenkonto-JSON. |
| `korrespondenz/services/kontext_service.py:250-255` | Platzhalter `ev.sepa_mandat_vorhanden/fehlt`. |

Achtung Namenskollision: `sepa_mandat_id` (CharField) in `buchhaltung/models.py:1291`,
`serializers_wkz.py`, `services/wkz/*` ist **nicht** der FK.

### Bestandsrisiko (Spec §10)
Im aktuellen Produktivpfad **kein Crash**: der Autopilot-Vorfilter schließt
Personen ohne Mandat aus, bevor `commite_lastschriftlauf` läuft. Verbleibende
Lücke: der Vorfilter ignoriert `aktiv=False` → ein deaktiviertes Mandat käme in
den Lauf (der View-Pfad prüft aktiv, der Autopilot nicht).

Dev-DB (immocore_backend_dev, nur lesend): 5 Mandate (alle aktiv), 623 Personen,
5 mit Mandat, 570 mit ≥1 aktivem EV, davon 566 ohne Mandat, 114 mit >1 aktivem EV,
1082 aktive EV, 0 geteilte Mandate. Prod (.50) nicht geprüft.

## V3 — Token-/Mail-/Bestätigungs-Flow (Signaturen)

### `PortalToken` — `backend/apps/portal/models.py:86-143`
TYP_EINLADUNG='einladung', TYP_MAGIC='magic', TYP_EMAIL_BESTAETIGUNG='email_bestaetigung'
(:100-107). Felder: zugang FK (related 'tokens'), typ Char30 choices, token Char100
unique (Klartext, `secrets.token_urlsafe(48)` in save :134-137), **ziel_email
EmailField** (:115-120), gueltig_bis, verbraucht_am (null), erstellt_am.
`ist_gueltig()` (:139). Keine `verbrauche()`-Methode (Verbrauch in `loese_token_ein`).
Konstanten (:31-34): EINLADUNG 72 h, MAGIC 15 min, EMAIL_BESTAETIGUNG 24 h, SESSION 12 h.

`PortalZugang` (:37-83): person OneToOne (related 'portal_zugang'), aktiv,
email_pending EmailField (:60-65). **Kein** eigenes email-Feld.

### `zugang_service.py`
| Funktion | Signatur | Zeile |
|---|---|---|
| `_erzeuge_token` | `(zugang, typ, gueltig_bis, ziel_email='') -> PortalToken` | :125 |
| `_entwerte_offene_token` | `(zugang, typ) -> None` | :131 |
| `erzeuge_email_bestaetigung` | `(zugang, neue_email: str) -> PortalToken` (atomic, entwertet alte, 24 h) | :219 |
| `loese_token_ein` | `(token_wert: str, erwartete_typen: tuple[str,...]) -> PortalToken`; wirft `TokenUngueltig`, `ZugangGesperrt`; select_for_update; setzt verbraucht_am | :234 |
| `pruefe_rate_limit` | `(email) -> None`, wirft `RateLimitErreicht`; nur in Views genutzt | :178 |
Exceptions: `PortalFehler`, `TokenUngueltig`, `ZugangGesperrt`, `RateLimitErreicht` (:35-48).

### `stammdaten_service.py`
| Funktion | Signatur | Zeile |
|---|---|---|
| `protokolliere` | `(person, feld: str, alter_wert: str, neuer_wert: str) -> None` | :90 |
| `stosse_email_aenderung_an` | `(zugang, neue_email: str) -> PortalToken` (atomic; wirft `StammdatenFehler`) | :253 |
| `bestaetige_email` | `(token_wert: str) -> Person` (atomic; wirft TokenUngueltig/ZugangGesperrt/StammdatenFehler) | :278 |
| `aktualisiere_bankverbindung` | `(zugang, daten: dict) -> dict` | :167 |

### `mail_service.py`
`email_bestaetigung_url(token) -> str` = `f'{FRONTEND_BASE_URL}/portal/email-bestaetigen/{token.token}'` (:77);
`versende_email_bestaetigung(token) -> None` (:143, Empfänger `token.ziel_email`);
`_sende(betreff, vorlage, empfaenger, kontext)` (:101) rendert `email/{vorlage}.txt|.html`.
Templates: **`backend/templates/email/`** (portal_einladung, portal_magic_link,
portal_email_bestaetigung je .txt/.html). Settings: `FRONTEND_BASE_URL`
(settings.py:222), `PORTAL_FROM_EMAIL` (:203). `VersandNichtKonfiguriert` (:33).

### Views/URLs (`backend/apps/portal/views.py`, `urls.py`)
| Pfad (unter /api/v1/) | View | Auth |
|---|---|---|
| `portal/meine-daten/email/` | `EmailAendernView.post` (:252) Body `email`; 400/503/200 | Session |
| `portal/meine-daten/email/bestaetigen/` | `EmailBestaetigenView.post` (:284) Body `token`; 400 `_UNGUELTIGER_LINK`/200 | AllowAny + ScopedRateThrottle 'portal_auth' |
| `portal/auth/magic-link/request/` | `MagicLinkAnfordernView` (:49), `_NEUTRALE_ANTWORT` (:43-45) immer 200 | AllowAny + Throttle |
| `portal/iban-check/` | `IbanPruefenView.get` (:206) Query `iban` → `{valid, iban, bic, bank_name}` | Session |
| `portal/meine-einheiten/` | `MeineEinheitenView` (:132) | Session |

Token aus Body: `TokenSerializer` (serializers.py:16, Feld `token`).

### Auth (`backend/apps/portal/auth.py`)
`PortalSessionAuthentication` (:22, Header `Authorization: Portal <token>`) setzt
`request.portal_session`, `request.portal_zugang`; `request.user` = `PortalNutzer`
mit `.zugang`, `.person` (:93-96). **`request.auth` ist None.** `IstPortalNutzer` (:102).
Grundregel Docstring :8-10: Person ausschließlich aus Sitzungs-Token.

### IBAN-Prüfung
**Keine Service-Funktion.** Inline `schwifty.IBAN(roh)` in `IbanPruefenView.get`
(views.py:221-249) und `BankverbindungSerializer.validate_iban` (serializers.py:80-91,
Fehler 'Diese IBAN ist ungültig.', bei ImportError keine Prüfung).
Tests: `portal/tests/test_iban_pruefung.py`.

### Testmuster (`backend/apps/portal/tests/`)
`basis.py`: `erstelle_objekt`, `erstelle_einheit(objekt, nr, lage, mea)`,
`erstelle_eigentuemer`, `verknuepfe(person, einheit, beginn, ende)`,
`erstelle_mandat(person, referenz, iban, bic, aktiv=True)`.
Klassen mit `@override_settings(EMAIL_BACKEND=locmem)`, `setUp`: `cache.clear()`,
`mail.outbox.clear()`, `lade_ein` → `melde_an` → `credentials(HTTP_AUTHORIZATION=f'Portal {token}')`.
Vorbild E-Mail-Flow: `test_stammdaten.py:211-299` (`EmailAenderungTest`).
Isolation: `test_einheiten_und_isolation.py:114` (`DatenisolationTest`).

Bekannte Lücken im Vorbild-Flow (für den neuen Flow beachten):
B1 `bestaetige_email` prüft Fremdzugehörigkeit nicht erneut; B2 `EmailAendernView`
ohne Throttle; B3 nur `VersandNichtKonfiguriert` gefangen, andere Mailfehler → 500
bei bereits angelegtem Token/Pending.

## V4 — Frontend

- `pages/portal/PortalLayout.tsx` (67 Z.): Guard inline (:18 `getPortalToken()`), kein
  Nutzer-State/Query, Nav :48-51 zwei `NavLink` (Meine Einheiten `/portal/einheiten`,
  Meine Daten `/portal/daten`), `linkClass` :27-32, Abmelden :52-57. Keine Breakpoints.
- `pages/portal/PortalEmailBestaetigen.tsx` (55 Z.): Token als **Path-Param**
  `useParams().token`; Route `/portal/email-bestaetigen/:token` (App.tsx:102, öffentlich);
  useEffect + useRef-Doppelaufrufschutz; Status 'laedt'|'ok'|'fehler'; Karte
  `bg-portal-brand` / `max-w-sm bg-white rounded-xl`.
- Routen App.tsx:100-107: öffentlich login, anmelden/:token, email-bestaetigen/:token;
  geschützt `/portal` → PortalLayout → einheiten, daten.
- `api/portal.ts` (359 Z.): `portalClient` axios baseURL `/api/v1/portal`, Header
  `Authorization: Portal <token>` (localStorage `portal_token`), 401-Interceptor.
  `ibanPruefen(iban): Promise<IbanCheckResult>` (:151); `emailAendern(email)` (:170);
  `emailBestaetigen(token)` (:176, anonym); `meineEinheiten(): Promise<PortalWegKarte[]>`
  (:127); `meineDaten(): Promise<PortalMeineDaten>` (:132, enthält `hat_aktives_mandat`,
  `mandatsreferenz`, `iban`, `bic`); `bankverbindungSpeichern` (:161).
  `PortalEinheit` (:59-67): einheit_id, einheit_nr, lage, nutzungsart,
  miteigentumsanteil, eigentum_seit, eigentum_bis — **keine ev_id**.
- `components/ui/IbanInput.tsx`: Props value, onChange, onBicFound?, pruefe?, disabled;
  in MeineDaten :188-195 mit `pruefe={ibanPruefen}`. `Button` variant 'portal' /
  'portal-secondary'. `Input` (label?, error?).
- **Kein generisches Modal** in components/ui; Muster: Inline-Overlay in
  `pages/korrespondenz/schreiben/SchreibenErstellenDialog.tsx:135-136`
  (`fixed inset-0 z-50 … bg-black/40`, role="dialog"). Im Portal bisher kein Dialog;
  E-Mail-Änderung ist Inline-Form (`EmailSektion` MeineDaten :220-284).
- react-query v5 (`['portal', …]`-Keys), reines Tailwind, keine Icon-Lib.
  Portal-Farben `tailwind.config.js:20-30` (`portal.brand #2f5d50`, brand-soft, ink,
  soft, paper, line, debit, credit).
- Frontend-Tests: vitest + testing-library; **keine** Portal-Tests vorhanden.

## V5 — "Aktives EV je Einheit"

- Portal-Definition (`portal/services/einheiten_service.py:59-66`):
  `beginn__lte=heute` und (`ende IS NULL` oder `ende >= heute`).
- Modell-Property `ist_aktiv` = `ende is None` (abweichend; EV mit künftigem Ende ist
  im Portal sichtbar, Property aber False).
- Reine `ende IS NULL`-Stellen: buchungserkennung, eigentuemerwechsel_service,
  ebanking_erkennungs_service, camt_matching_service, personen/views, kontext_service,
  stimmkraft_service u. a. Periodenbezogen: sollstellungslauf_service (`exclude(ende__lt=periode)`).
- `meine_einheiten(person) -> list[dict]` (:53): WEG-Karten mit `einheit_id`,
  `einheit_nr`, `lage`, `nutzungsart`, `miteigentumsanteil`, `eigentum_seit`,
  `eigentum_bis`. **Keine Funktion zur Zugehörigkeitsprüfung einer EV-/Einheiten-ID**;
  Isolation rein über `filter(person=person)`.
- Einzug: Kandidaten = `HausgeldSollstellung` eines Sollstellungslaufs, je EV
  (auto_pipeline_service.py:168-171); Gruppierung in `commite_lastschriftlauf` je `ev.id`.
- Tests Lastschrift: `buchhaltung/tests/test_lastschrift_end_to_end.py`,
  `test_lastschrift_erloesbuchung.py`, `test_auto_pipeline_service.py` (Ausschluss
  kein_sepa_mandat ~:222-235, FRST ~:332-365).
- Testlauf: Django-Runner, im Dev-Container:
  `docker compose exec backend python manage.py test apps.portal` bzw.
  `… test apps.buchhaltung.tests.test_lastschrift_end_to_end apps.buchhaltung.tests.test_lastschrift_erloesbuchung apps.buchhaltung.tests.test_auto_pipeline_service`.
  Braucht Postgres + Redis (Cache). Kein pytest.

## Abweichungen Spec ↔ Ist (für Angleichung nach HALT 0)

| # | Spec | Ist | Konsequenz |
|---|---|---|---|
| A1 | §4.3 Resolver ersetzt nur `sepa_lastschrift.py:220` | Mandatswahl an **drei** Stellen: Autopilot-Vorfilter (`auto_pipeline_service.py:174-199`), Lauf (`sepa_lastschrift.py:220`), View (`buchhaltung/views.py:1510-1517`) | Resolver muss alle drei bedienen (R2: eine Funktion); Vorfilter braucht EV-bezogen statt person-bezogen |
| A2 | §10 Crash bei Person ohne Mandat | Vorfilter verhindert Crash; **aktiv-Check fehlt** im Vorfilter | Resolver liefert nur aktive Mandate → schließt Lücke mit |
| A3 | §4.2 Token-Bindung "wie ziel_email" | `ziel_email` ist EmailField, für IBAN ungeeignet | Architekt: FK Token→Pending oder Pending-FK→Token |
| A4 | §3 IBAN-Prüfung "bestehend wiederverwenden" | keine Service-Funktion, nur inline schwifty in View + Serializer | kleine Helper-Funktion extrahieren oder `BankverbindungSerializer.validate_iban` nutzen |
| A5 | §6.3 Route "z. B. /portal/sepa-mandat/bestaetigen" + Token aus URL | Vorbild nutzt Path-Param `:token` | Route `/portal/sepa-mandat/bestaetigen/:token`, URL-Builder analog `email_bestaetigung_url` |
| A6 | §6.2 Dialog, Einheitenauswahl | kein Modal im Portal; `PortalEinheit` hat keine `ev_id` | Dialog neu nach Overlay-Muster; GET `/sepa-mandat/` liefert Einheitenliste **mit ev_id** (R8-tauglich, Zugehörigkeit serverseitig) |
| A7 | §5 Pfad `apps/portal/views*.py` | eine `views.py`; Einheiten-Endpunkt heißt `meine-einheiten/` | Namensgebung neuer Endpunkte an `portal/sepa-mandat/…` anlehnen |
| A8 | §5.5 Template-Ort `templates/email/` | `backend/templates/email/` | ok, Pfad präzisiert |
| A9 | R8 "Person/Einheit aus Sitzung" | `request.portal_zugang.person` / `request.user.person`; `request.auth` ist None | Builder-Anweisung |
| A10 | "aktives EV" | zwei Definitionen (Portal: ende null/≥heute; Property: ende is None) | Architekt legt Resolver-Definition fest |
| A11 | §4.1 Person.sepa_mandat "Einzel-FK" | FK many-to-one (`related_name='personen'`), nicht OneToOne | Migration: Sammelmandat-Zuordnung je Person; geteilte Mandate (0 in Dev) explizit behandeln |
| A12 | §1 R4 Zustand | `PortalMeineDaten.hat_aktives_mandat` existiert bereits (personenweit) | GET `/sepa-mandat/` liefert Zustand je Geltungsbereich; `hat_aktives_mandat` bleibt kompatibel |
