# Architektur-Entscheid (Phase 1 / HALT-A) — Portal: SEPA-Lastschriftmandat

Erstellt 2026-11-03 durch `immo-architect` (Opus), vom Orchestrator gegen Spec
(`docs/CLAUDE_CODE_ANLEITUNG_PORTAL_SEPA_MANDAT_v1_0.md` inkl. §11) und
`IST_BERICHT_PORTAL_SEPA_MANDAT.md` geprüft. Code-Behauptungen K1 und K3 sowie
`Personenkonto.vertrag` wurden vom Orchestrator im Code verifiziert
(sepa_lastschrift.py:270, buchhaltung/views.py:1573, objekte/models.py:32,
konten/models.py:92). **Status: wartet auf Freigabe durch Patrik.**

## Vorab: drei Punkte, die die Spec nicht abdeckt

- **K1 – FRST blockiert das Feature dauerhaft.** Spec §5.2 sieht
  `sequence_type='FRST'` vor. Der Autopilot schließt FRST aus
  (`mandat_typ_frst`, auto_pipeline_service.py:184), keine Stelle setzt FRST je
  auf RCUR, beide pain.008-Pfade senden fest `'RCUR'` (sepa_lastschrift.py:270,
  views.py:1573). → Festlegung (a): RCUR.
- **K2 – Zweiter Änderungsweg ohne Magic Link.**
  `stammdaten_service.aktualisiere_bankverbindung` (:166-245) ändert die
  Mandats-IBAN heute sofort (R3-Verstoß, bei geteilten Mandaten fremde Personen
  betroffen). → ab v1 nur noch `Person.ibans`, kein Mandat.
- **K3 – Gläubiger-ID hängt am Objekt** (`Objekt.glaeubiger_id`). Ein
  Sammelmandat über mehrere WEGs ist rechtlich mehrere Mandate an verschiedene
  Gläubiger. → (b) `abgedeckte_glaeubiger` festhalten; rechtliche Prüfung.

## (a) Datenmodell

**Entscheidung:** Einzelne FKs am Mandat, kein Through-Modell.
- `SEPAMandat.person` = FK(Person, PROTECT, null=True, blank=True, related_name='sepa_mandate')
- `SEPAMandat.eigentumsverhaeltnis` = FK(EigentumsVerhaeltnis, **PROTECT**, null=True, blank=True, related_name='sepa_mandate'); NULL = Sammelmandat
- `SEPAMandat.quelle` = CharField(20, choices verwaltung/portal, default 'verwaltung')
- `person` bleibt in v1 **nullable** (Admin, `SEPAMandatViewSet`, Test-Helfer
  `erstelle_mandat` legen Mandate ohne Person an). CheckConstraint
  `ck_mandat_ev_braucht_person`: `eigentumsverhaeltnis IS NULL OR person IS NOT NULL`.
- Nicht SET_NULL am EV (sonst würde ein Einheitenmandat still zum Sammelmandat).
  Folge: Einheit/EV mit Mandat nicht mehr löschbar.
- Höchstens ein aktives Mandat je Geltungsbereich, zwei partielle UniqueConstraints:
  - `uniq_aktives_mandat_je_ev`: fields=['eigentumsverhaeltnis'], condition `Q(aktiv=True, eigentumsverhaeltnis__isnull=False)`
  - `uniq_aktives_sammelmandat_je_person`: fields=['person'], condition `Q(aktiv=True, eigentumsverhaeltnis__isnull=True)`
- **`Person.sepa_mandat` bleibt** als Legacy-Spiegel des Sammelmandats. Nur der
  neue Service setzt ihn (beim Anlegen eines Sammelmandats). Einheitenmandate
  fassen ihn nie an. Resolver fällt auf ihn zurück (siehe d).
- Lesestellen, die auf den Resolver umgestellt werden: `kontext_service.py:250`
  (sonst falsche Platzhalter), `konten/views.py:320` (`pk.vertrag` = EV →
  `mandate_fuer_evs` im Bulk), `stammdaten_service.aktives_mandat` →
  `sammelmandat_fuer_person`. Unverändert: `personen/serializers.py`, Admin
  (nur neue Felder ergänzen).
- **Datenmigration** (RunPython, idempotent über `person IS NULL`, rückwärts
  noop): Mandat mit genau einer referenzierenden Person → `person` setzen,
  `eigentumsverhaeltnis` bleibt NULL. 0 oder ≥2 Referenten → nicht anfassen, nur
  loggen (Legacy-Rückfall hält heutiges Verhalten). Kein Klonen (neue Referenz
  wurde nie erteilt), kein Abbruch.
- Reihenfolge: Felder nullable → RunPython → Constraints.
- **Änderung = IBAN/BIC in-place** am bestehenden Mandat; `mandatsreferenz`,
  `unterzeichnet_am`, `sequence_type` bleiben (SEPA-Mandatsänderung mit gleicher
  Referenz; seit Rulebook 11/2016 bei Bankwechsel keine neue FRST nötig).
- **Portal-Mandate bekommen `sequence_type='RCUR'`** (Abweichung von Spec §5.2):
  FRST ist seit 11/2016 optional, das System erzeugt ohnehin nie FRST im XML, mit
  RCUR zieht der Autopilot beim nächsten Lauf. Sonst wäre das Feature für den
  Autopilot wirkungslos.
- Änderungen an **geteilten Mandaten** (>1 Person oder `mandat.person` ≠
  Antragsteller) lehnt das Portal ab („Bitte wenden Sie sich an die Verwaltung").
- **K2:** `aktualisiere_bankverbindung` schreibt nur noch `Person.ibans`; die
  Bankverbindungs-Sektion in MeineDaten verweist auf den Dialog.

**Risiken:** Autopilot behandelt inaktive Mandate künftig als
`kein_sepa_mandat` (schließt Lücke A2, ändert Prod-Verhalten). pain.008 sendet
bei IBAN-Änderung keine Amendment-Info (SMNDA) — heute schon so, optional v1.1.

**Freigabe nötig: ja** (RCUR statt FRST, K2, Datenmigration auf Prod).

## (b) Nachweis „per Magic Link bestätigt"

**Entscheidung:** `PortalSepaMandatAenderung` ist Antrag **und** unveränderlicher
Nachweis. FKs PROTECT (`zugang`, `person`, `mandat`). Admin nur lesend; nach
`bestaetigt` ändert der Service nichts mehr. `PersonStammdatenAenderung`
bekommt den GoBD-Eintrag mit Verweis `Nachweis <id>`. Am `SEPAMandat` nur
`quelle='portal'`.

| Zeitpunkt | Felder |
|---|---|
| Anfordern | `erstellt_am`, `anforderung_ip`, `anforderung_user_agent`, `portal_session_id` (UUID-Kopie) |
| Versand | `empfaenger_email`, `mail_versendet_am` |
| Mandatstext | `mandatstext` (vollständig gerendert), `mandatstext_version` (z. B. 'SEPA-CORE-PORTAL-1'), `mandatstext_sha256` |
| Mandatsdaten | `mandatsreferenz`, `iban`, `bic`, `kontoinhaber_name`, `abgedeckte_glaeubiger` (JSON: objekt_id, Bezeichnung, Gläubiger-ID, ev_ids) |
| Bestätigung | `bestaetigt_am`, `bestaetigung_ip`, `bestaetigung_user_agent`, `forwarded_for_roh`, `kontoinhaber_erklaerung` (Bool) |

- Mandatstext: Gläubiger (WEG) + Gläubiger-ID je abgedeckter WEG,
  Mandatsreferenz, Kontoinhaber, IBAN/BIC, wiederkehrend, Standard-Ermächtigung
  mit 8-Wochen-Hinweis, Vorabankündigungsklausel. Beim Anfordern gerendert,
  identisch in Mail und Bestätigungsseite.
- **Kein Auto-Bestätigen beim Laden** (Abweichung vom Vorbild
  `PortalEmailBestaetigen` und von Spec §6.3): Mail-Scanner (Safe Links) führen
  JS aus. Seite holt Vorschau per nicht verbrauchendem GET; Zustimmung per
  Checkbox „Ich bin Kontoinhaber…" + Button „Mandat verbindlich erteilen". Der
  Zustimmungszeitpunkt ist dieser POST.
- Mail-Empfänger ist `person_email(person)`, nicht `zustell_email`
  (Bevollmächtigter ist nicht Kontoinhaber). Fehlt die eigene Adresse → Ablehnung.
- `client_ip(request)`: `X-Real-IP` → erster `X-Forwarded-For` → `REMOTE_ADDR`; Rohwert mitspeichern.
- Nach Bestätigung: Bestätigungsmail (Mandatstext, Referenz, Gläubiger-ID) per
  `on_commit`; Fehler nur loggen.
- K3: Objekt ohne `glaeubiger_id` → Anfrage ablehnen. `abgedeckte_glaeubiger`
  erlaubt spätere Beschränkung des Sammelmandats ohne Datenverlust.

**Risiken:** Header fälschbar, wenn Backend direkt erreichbar. Ohne
Ausweisprüfung belegt das Verfahren nur „Inhaber von Postfach und Portal-Sitzung".
**Freigabe nötig: ja, mit rechtlicher Prüfung** (Liste unten).

## (c) Mandatsreferenz

`PORTAL-{PNR}-{LFD:03d}`, Beispiel `PORTAL-100234-001`. PNR =
`Person.personennummer` (A-Z0-9, max. 20), sonst `P` + 10 Hex der UUID. Max. 31
Zeichen, nur `A-Z 0-9 -`. Präfix grenzt gegen Bestand (`M2024-090`) und
Test-Helfer ab. Kein EV/Einheit/Datum (UUID zu lang, einheit_nr nicht
eindeutig, Datum in `unterzeichnet_am`). Erzeugt beim Anfordern (steht im
Mandatstext), auf dem Pending gespeichert; LFD = max über SEPAMandat + offene
Pendings der Person + 1. Bei IntegrityError beim Bestätigen → „bitte neu
anfordern", nicht still neu nummerieren.
**Freigabe nötig: nein** (Präfix frei wählbar).

## (d) Resolver

**Ort:** `backend/apps/personen/services/sepa_mandat.py` (Modell in personen;
Buchhaltung und Portal hängen beide davon ab, kein Zyklus).
```python
def mandate_fuer_evs(evs: Iterable[EigentumsVerhaeltnis]) -> dict[UUID, SEPAMandat | None]
def mandat_fuer_ev(ev: EigentumsVerhaeltnis) -> SEPAMandat | None      # = mandate_fuer_evs([ev])[ev.id]
def sammelmandat_fuer_person(person: Person) -> SEPAMandat | None
```
Rangfolge (R2) nur in privater `_waehle(ev, spezifisch, sammel, legacy)`:
1. aktives Mandat mit `eigentumsverhaeltnis_id == ev.id`
2. aktives Mandat mit `person_id == ev.person_id` und EV NULL
3. Legacy-Rückfall `ev.person.sepa_mandat`, sofern aktiv, EV NULL, `person_id in (None, ev.person_id)`
4. None

„Aktiv" = nur `SEPAMandat.aktiv=True`; EV-Aktivität prüft der Resolver nicht
(Fälligkeit entscheidet der Sollstellungslauf; letzter Einzug eines Verkäufers
muss laufen). Portal-EV-Definition gilt nur für Auswahlliste und erneute Prüfung
beim Bestätigen. `mandate_fuer_evs` = eine Abfrage (`filter(aktiv=True)` mit
ODER aus `eigentumsverhaeltnis_id__in`, `(person_id__in, ev isnull)`,
`id__in(legacy_ids)`). Aufrufer: `select_related('eigentumsverhaeltnis__person',
'eigentumsverhaeltnis__einheit')`.

Umstellung: Autopilot-Vorfilter (Map vor der Schleife; Warnungstypen/Texte
bleiben), `commite_lastschriftlauf` (None → `continue` + `logger.warning`),
`buchhaltung/views.py:1507-1517` (`if not mandat`; FRST bleibt im manuellen Pfad
zugelassen), plus kontext_service, konten/views, `aktives_mandat`.
**Freigabe nötig: nein.**

## (e) Token ↔ Pending

**Entscheidung:** `PortalSepaMandatAenderung.token = OneToOneField(PortalToken,
PROTECT, null=True, related_name='sepa_mandat_aenderung')`. Am Token nur die
Choice `TYP_SEPA_MANDAT='sepa_mandat'`; `SEPA_MANDAT_BESTAETIGUNG_GUELTIG_STUNDEN=24`.

Status: `offen` → `bestaetigt` | `verworfen` (neues Anfordern oder
Zustandskonflikt) | `verfallen` (lazy bei GET-Status/Anfordern, kein Cron).
UniqueConstraint `uniq_offene_sepa_anfrage_je_zugang` (zugang, status='offen').

`stosse_mandat_an` (atomic, Mailversand letzter Schritt **in** der Transaktion →
Mailfehler rollt Pending+Token zurück, schließt B3): IBAN prüfen → EV gehört
zur Person und ist Portal-aktiv → `aktion`/`ziel_mandat` → offene Pendings
verwerfen + `_entwerte_offene_token(zugang, TYP_SEPA_MANDAT)` → Referenz +
Mandatstext → Pending + Token → Mail. Throttle `ScopedRateThrottle`
`'portal_sepa_mandat': '5/hour'` (schließt B2). Klare Fehler 400/429/503.

`bestaetige_mandat(token_wert, *, ip, user_agent, forwarded_roh,
kontoinhaber_erklaerung)` (atomic): `loese_token_ein(..., (TYP_SEPA_MANDAT,))`,
Pending per `select_for_update` + `status=='offen'`. Erneute Prüfung (schließt
B1): bei `einheit` EV weiterhin der Person und Portal-aktiv; bei `anlage` darf
inzwischen **kein** aktives Mandat im Geltungsbereich existieren (sonst
`verworfen`, „bitte neu anfordern", nicht umdeuten); bei `aenderung`
`ziel_mandat` noch aktiv, gleicher Geltungsbereich, nicht geteilt. Ohne
`kontoinhaber_erklaerung=True` keine Wirkung. Dann anwenden (RCUR,
`unterzeichnet_am=heute`, `quelle='portal'`, bei Sammelmandat Legacy-FK) oder
IBAN/BIC in-place; `Person.ibans` (R7); `protokolliere(..., quelle='Portal-Magic-Link')`;
Bestätigungsmail per `on_commit`. `protokolliere` bekommt optionalen Parameter
`quelle: str = QUELLE_PORTAL`.

Helfer: `zugang_service.pruefe_token(token_wert, erwartete_typen)` (nicht verbrauchend).
Endpunkte: `GET portal/sepa-mandat/bestaetigen/<token>/` (Vorschau), `POST
portal/sepa-mandat/bestaetigen/` (Body `token`, `kontoinhaber_erklaerung`), beide
AllowAny + Throttle `portal_auth`.
**Freigabe nötig: nein.**

## (f) `GET /portal/sepa-mandat/`

Server liefert die Aktion je Geltungsbereich; Frontend leitet nichts ab.
```json
{
  "kann_erteilen": true,
  "hinderungsgrund": null,
  "empfaenger_email_maskiert": "p***@example.de",
  "kopfzeile_aktion": "erteilen|aendern",
  "auswahl_noetig": true,
  "geltungsbereiche": [
    {"schluessel": "alle", "ev_id": null, "bezeichnung": "Alle Einheiten",
     "aktion": "erteilen|aendern",
     "mandat": {"mandatsreferenz": "...", "iban_maskiert": "DE89 **** **** **** **30 00",
                "bic": "...", "unterzeichnet_am": "YYYY-MM-DD", "quelle": "verwaltung|portal"}},
    {"schluessel": "ev:<uuid>", "ev_id": "<uuid>", "objekt_bezeichnung": "...",
     "einheit_nr": "...", "lage": "...", "aktion": "erteilen|aendern", "mandat": null,
     "wirksam_ueber": "einheit|alle|keins"}
  ],
  "offene_anfrage": {"schluessel": "...", "aktion": "...", "erstellt_am": "...", "gueltig_bis": "..."}
}
```
`hinderungsgrund` bei fehlender eigener E-Mail, keinem aktiven EV oder nur
geteiltem Mandat. `kopfzeile_aktion` = `aendern`, sobald irgendein Bereich
`aendern` hat. `auswahl_noetig` bei >1 aktivem EV. Bei genau einem EV nur ein
Eintrag: Einheitenmandat vorhanden → `ev:` mit `aendern`, sonst `alle` (Anlage
wird Sammelmandat, damit Legacy-Leser und `hat_aktives_mandat` es sehen).
Isolation (R8): POST Anfordern nimmt `schluessel`, Server löst nur gegen die
eigene Liste auf.
**Freigabe nötig: nein.**

## Festlegungen für immo-builder

| Bereich | Festlegung |
|---|---|
| `personen/models.py` SEPAMandat | `person` FK(Person, PROTECT, null, blank, related_name='sepa_mandate'); `eigentumsverhaeltnis` FK(EigentumsVerhaeltnis, PROTECT, null, blank, related_name='sepa_mandate'); `quelle` Char20 ('verwaltung','portal') default 'verwaltung'; Check `ck_mandat_ev_braucht_person`; Unique `uniq_aktives_mandat_je_ev`, `uniq_aktives_sammelmandat_je_person` |
| Migrationen personen | Felder → RunPython (genau 1 Referent → person; idempotent über `person IS NULL`; rückwärts noop) → Constraints |
| `portal/models.py` | `PortalToken.TYP_SEPA_MANDAT='sepa_mandat'` + Choice; `SEPA_MANDAT_BESTAETIGUNG_GUELTIG_STUNDEN=24`; `PersonStammdatenAenderung.QUELLE_PORTAL_MAGIC_LINK='Portal-Magic-Link'` |
| `PortalSepaMandatAenderung` (portal) | id UUID; zugang FK PROTECT; person FK PROTECT; `geltungsbereich` Char10 ('alle','einheit'); eigentumsverhaeltnis FK PROTECT null; `aktion` Char10 ('anlage','aenderung'); ziel_mandat FK(SEPAMandat, PROTECT, null, related_name='+'); mandat FK(SEPAMandat, PROTECT, null, related_name='portal_nachweise'); token OneToOne(PortalToken, PROTECT, null, related_name='sepa_mandat_aenderung'); `status` Char10 ('offen','bestaetigt','verfallen','verworfen'); mandatsreferenz Char35; iban Char34; bic Char11 blank; kontoinhaber_name Char140; mandatstext Text; mandatstext_version Char30; mandatstext_sha256 Char64; abgedeckte_glaeubiger JSON; empfaenger_email Email; erstellt_am auto; mail_versendet_am DT null; anforderung_ip GenericIP null; anforderung_user_agent Text; portal_session_id UUID null; bestaetigt_am DT null; bestaetigung_ip GenericIP null; bestaetigung_user_agent Text; forwarded_for_roh Char255; kontoinhaber_erklaerung Bool default False; verworfen_grund Char200. Unique `uniq_offene_sepa_anfrage_je_zugang`. Admin nur lesend. |
| Resolver | `personen/services/sepa_mandat.py`: `mandate_fuer_evs`, `mandat_fuer_ev`, `sammelmandat_fuer_person`, privat `_waehle` |
| Portal-Service | `portal/services/sepa_mandat_service.py`: `status_fuer_zugang(zugang) -> dict`; `stosse_mandat_an(zugang, schluessel: str, iban: str, bic: str, *, ip, user_agent, session_id) -> PortalSepaMandatAenderung`; `vorschau(token_wert) -> dict`; `bestaetige_mandat(token_wert, *, ip, user_agent, forwarded_roh, kontoinhaber_erklaerung: bool) -> SEPAMandat`; `erzeuge_mandatsreferenz(person) -> str` |
| zugang_service | `erzeuge_sepa_mandat_token(zugang) -> PortalToken` (atomic, entwertet alte); `pruefe_token(token_wert, erwartete_typen) -> PortalToken` |
| stammdaten_service | `protokolliere(..., quelle=QUELLE_PORTAL)`; `aktives_mandat` → `sammelmandat_fuer_person`; `aktualisiere_bankverbindung` ohne Mandats-Schreibzugriff (K2) |
| Hilfsfunktionen | `client_ip(request) -> tuple[str or None, str]`; IBAN-Helper aus `IbanPruefenView` extrahieren |
| Mail | `mail_service.sepa_mandat_url(token)` → `/portal/sepa-mandat/bestaetigen/{token}`; `versende_sepa_mandat_link(pending)`, `versende_sepa_mandat_bestaetigung(pending)`; Templates `backend/templates/email/portal_sepa_mandat.(txt|html)`, `portal_sepa_mandat_bestaetigt.(txt|html)` |
| Endpunkte | `GET portal/sepa-mandat/` (Session); `POST portal/sepa-mandat/anfordern/` (Session, Throttle `portal_sepa_mandat` '5/hour'); `GET portal/sepa-mandat/bestaetigen/<token>/`, `POST portal/sepa-mandat/bestaetigen/` (AllowAny, `portal_auth`) |
| Umstellung Lesestellen | `auto_pipeline_service.py:158-206`, `sepa_lastschrift.py:216-238`, `buchhaltung/views.py:1507-1517`, `korrespondenz/services/kontext_service.py:247-256`, `konten/views.py:296-320` |
| Frontend | Bestätigungsseite **ohne** Auto-POST: Vorschau laden, Checkbox Kontoinhaber, Button. Route `/portal/sepa-mandat/bestaetigen/:token` |

## Patrik muss freigeben

1. **RCUR statt FRST** für Portal-Mandate (Abweichung von Spec §5.2). **Freigegeben durch Patrik am 2026-11-04: Portal-Mandate werden immer mit RCUR angelegt.** Rückfrage bei Hausbank/Windata empfohlen, ob eine Erstlastschrift als RCUR angenommen wird.
2. **K2:** „Meine Daten → Bankverbindung" ändert kein Mandat mehr; nur noch Magic-Link-Flow. Ändert Bestandsverhalten.
3. **Autopilot-Verhaltensänderung:** inaktive Mandate werden künftig ausgeschlossen (`kein_sepa_mandat`).
4. **Bestätigung per Checkbox + Button** statt reinem Link-Klick (Abweichung von Spec §1.3/R3-Wortlaut und §6.3).
5. **Datenmigration auf Prod (.50)** erst nach diesen Lese-Abfragen: Mandate mit >1 referenzierender Person; Mandate ohne Person; Personen mit inaktivem `sepa_mandat`; Anzahl FRST-Mandate; Referenzen mit `PORTAL-` (Soll 0); Objekte mit EVs ohne `glaeubiger_id`.
6. **Rechtlich prüfen lassen** (nicht technisch entscheidbar):
   - a. Elektronisch erteiltes Mandat (Textform, ohne Unterschrift) gegenüber der eigenen Bank zulässig? Inkassovereinbarung anzupassen?
   - b. Darf ein Sammelmandat **mehrere Gläubiger** (WEGs mit eigener Gläubiger-ID) umfassen (K3)? Erfasst es später erworbene Einheiten in neuen WEGs? Falls nein: Beschränkung auf `abgedeckte_glaeubiger` (v1.1).
   - c. Endgültiger **Mandatstext** inkl. Vorabankündigungsfrist; ist die Vorabankündigung durch Wirtschaftsplan/Hausgeldbescheid abgedeckt?
   - d. Kontoinhaber ≠ Eigentümer in v1 ausgeschlossen (Pflicht-Erklärung); solche Fälle per Papier. OK?
   - e. Aufbewahrung des Nachweises (≥14 Monate nach letzter Lastschrift; AO/HGB 6/10 Jahre); IP/User-Agent in Datenschutzhinweise aufnehmen.
7. **Infrastruktur:** nginx auf .50/.51 setzt `X-Real-IP`/`X-Forwarded-For`; Backend (:8001) nicht direkt von außen erreichbar.
8. **Nicht in v1:** Entfernen von `Person.sepa_mandat`; Amendment-Info (SMNDA) in pain.008.
