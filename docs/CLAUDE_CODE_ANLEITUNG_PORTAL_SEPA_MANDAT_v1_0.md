# Claude-Code-Anleitung — Portal: SEPA-Lastschriftmandat erteilen & ändern (v1.0)

> **Anwendung:** In eine **Fable-5**-Claude-Code-Session einfügen. Fable ist
> ausschließlich **Orchestrator und Qualitätsprüfer** und schreibt **keinen
> Produktivcode selbst**. Jede konkrete Arbeit geht über das Agent-Tool an
> `immo-explorer` (Haiku, lesend), `immo-builder` (Sonnet, Umsetzung) oder
> `immo-architect` (Opus, Urteilsfragen). Voraussetzung: die drei Worker liegen
> in `.claude/agents/` und die Session wurde einmal neu gestartet.
>
> Diese Spec folgt dem Muster von `FABLE5_ORCHESTRATOR_PROMPT_BELEG_DOKUMENT.md`
> und `CLAUDE_CODE_ANLEITUNG_PORTAL_LAYOUT_UPDATE_v1_0.md`.

---

## 0. Ist-Befund (vorab erhoben, 2026-11-03)

**Zentrale Frage: Kann einem Eigentümer heute schon mehr als eine
Bankverbindung zugeordnet werden? → Nein, nicht im fachlich benötigten Sinn.**

Belegt am Code:

| Befund | Fundstelle |
|---|---|
| Ein Eigentümer hat **genau ein** aktives SEPA-Mandat (Einzel-FK). | `backend/apps/personen/models.py:125` — `Person.sepa_mandat = ForeignKey(SEPAMandat, …)` |
| `Person.ibans` ist eine JSON-Liste — es lassen sich **mehrere IBANs als Text** hinterlegen, aber nur zur **E-Banking-Zuordnung** eingehender Zahlungen, **nicht** als mehrere nutzbare Mandate. | `backend/apps/personen/models.py:122`; Begründung in `backend/apps/portal/services/stammdaten_service.py:178-181` |
| Der Lastschrifteinzug gruppiert je **Eigentumsverhältnis** (Einheit), zieht aber **immer** vom einen `person.sepa_mandat` ein — unabhängig davon, wie viele Einheiten der Eigentümer hält. | `backend/apps/buchhaltung/services/sepa_lastschrift.py:216-238` (`mandat = person.sepa_mandat`) |
| Es gibt **kein** Mandat und **keine** Bankverbindung je Einheit / je `EigentumsVerhaeltnis`. Das `objekte.Bankkonto` ist das **Bewirtschaftungskonto der Verwaltung**, nicht das des Eigentümers. | `backend/apps/buchhaltung/services/sepa_lastschrift.py:198-205` |
| Der Portal-Stammdaten-Service **ändert nur ein vorhandenes** Mandat (IBAN/BIC), erstellt **nie** eines, und dokumentiert ausdrücklich „ein Mandat je Person, nicht je Einheit". | `backend/apps/portal/services/stammdaten_service.py:10-16, 146-245` |
| SEPA-Mandate werden heute **ausschließlich im Django-Admin** angelegt; es gibt keinen Self-Service-Anlageweg und keine Mandats-Dokumenterzeugung. | `backend/apps/personen/admin.py:17-23`; kein `SEPAMandat.objects.create(...)` im Produktivcode |

**Folge für dieses Feature:** Der Wunsch „Mandat für **eine** Wohnung **oder
für alle**" ist mit dem heutigen Modell **nicht abbildbar**. Er erfordert eine
**Datenmodell-Änderung** (Mandat je Einheit zuordenbar) plus einen **neuen
Self-Service-Anlage-/Änderungs-Flow mit Magic-Link-Bestätigung**. Die
Magic-Link-Bausteine existieren bereits und werden wiederverwendet (siehe §4).

---

## 1. Ziel & Scope

Im Eigentümer-Portal soll der Eigentümer sein SEPA-Lastschriftmandat **selbst
erteilen und ändern** können:

1. In der **Kopfzeile** des Portals (neben „Meine Einheiten / Meine Daten")
   steht ein Button **„SEPA-Lastschriftmandat"**.
2. Klick öffnet einen Dialog. Hat der Eigentümer **mehrere Einheiten**, wählt er,
   ob das Mandat **für eine bestimmte Einheit** oder **für alle Einheiten** gelten
   soll. Bei nur einer Einheit entfällt die Auswahl.
3. Die **Erteilung** wird **per Magic Link** (E-Mail) bestätigt und erst damit
   wirksam.
4. Ist **bereits ein Mandat vorhanden**, heißt die Funktion **„SEPA-Lastschrift­
   mandat ändern"**. Auch die Änderung wird **per Magic Link** bestätigt.

**In Scope:** Mandat je Einheit *oder* Sammelmandat (alle Einheiten); Anlage und
Änderung; Magic-Link-Bestätigung; Audit-Protokoll (GoBD); Button + Dialog +
Bestätigungsseite im Portal; Resolver, damit der Lastschrifteinzug das richtige
Mandat je Einheit zieht.

**Out of Scope (v1):** Mandats-PDF/Papier-Erzeugung; Mandats-Widerruf/-Löschung
durch den Eigentümer (nur Verwaltung); Mandate für Mieter; Änderung von
`sequence_type` durch den Eigentümer (bleibt Automatik des Einzugs).

---

## 2. Fachliche Regeln (verbindlich)

- **R1** Ein Mandat gilt entweder für **genau ein** Eigentumsverhältnis (Einheit)
  oder als **Sammelmandat für alle** Einheiten des Eigentümers.
- **R2** Beim Einzug gilt pro Einheit: **einheitenspezifisches** aktives Mandat
  schlägt **Sammelmandat** → schlägt „kein Mandat" (dann kein Einzug für diese
  Einheit). Diese Rangfolge lebt in **genau einer** Resolver-Funktion (§4.3).
- **R3** Weder Anlage noch Änderung wird **ohne bestätigten Magic Link** wirksam.
  Der Klick auf den Magic Link ist der protokollierte Zustimmungszeitpunkt
  (`unterzeichnet_am`, Zeitstempel, Quelle „Portal-Magic-Link").
- **R4** Button-/Dialog-Beschriftung ist **zustandsabhängig**: existiert für den
  gewählten Geltungsbereich bereits ein aktives Mandat → „**ändern**", sonst
  „**erteilen**".
- **R5** Die IBAN wird **vor** dem Versand des Magic Links geprüft (bestehende
  IBAN-Prüfung wiederverwenden, siehe `backend/apps/portal/tests/test_iban_pruefung.py`).
- **R6** **GoBD:** jede wirksam gewordene Anlage/Änderung erzeugt einen
  `PersonStammdatenAenderung`-Eintrag (bestehende Protokollfunktion
  `stammdaten_service.protokolliere`).
- **R7** Die bisherige IBAN bleibt wie heute in `Person.ibans` erhalten (neue an
  Position 0) — die E-Banking-Zuordnung braucht sie (`stammdaten_service.py:178-181`).
- **R8** **Isolation:** die Person/Einheit kommt **ausschließlich** aus der
  Portal-Sitzung bzw. aus dem signierten Token-Zustand, **nie** aus einer vom
  Client gesendeten ID (Grundregel `backend/apps/portal/auth.py`).

---

## 3. Wiederverwendbare Bausteine (nicht neu bauen)

| Zweck | Vorhandenes Teil |
|---|---|
| Einmal-Link mit Ablauf & Einmalverwendung | `PortalToken` (`backend/apps/portal/models.py:86-144`), Typen `einladung`/`magic`/`email_bestaetigung` |
| Pending-Änderung + Bestätigungs-Flow (Vorbild!) | E-Mail-Änderung: `stammdaten_service.stosse_email_aenderung_an` / `bestaetige_email` (`backend/apps/portal/services/stammdaten_service.py:252-303`) |
| Token erzeugen / einlösen | `zugang_service.erzeuge_email_bestaetigung`, `zugang_service.loese_token_ein` (`backend/apps/portal/services/zugang_service.py:219-234`) |
| Magic-Link-Mail versenden + URL bauen | `mail_service.versende_email_bestaetigung`, `mail_service.email_bestaetigung_url` (`backend/apps/portal/services/mail_service.py`) + Templates unter `backend/.../templates/email/` |
| Bestätigungsseite im Frontend (Vorbild!) | `frontend/src/pages/portal/PortalEmailBestaetigen.tsx` + Route |
| IBAN-Prüfung | bestehender Endpoint `ibanPruefen` (`frontend/src/api/portal.ts`, `apps/portal/tests/test_iban_pruefung.py`) |
| Aktive Einheiten des Eigentümers | `apps/portal/services/einheiten_service.py` + `EigentumsVerhaeltnis` (aktiv = `ende IS NULL`) |
| Kopfzeile des Portals | `frontend/src/pages/portal/PortalLayout.tsx` (Header mit Nav + Abmelden) |

---

## 4. Architektur-Entscheidungen

> **Die endgültige Modellform ist ein HALT für `immo-architect` (Phase 1).**
> Unten steht die **empfohlene** Richtung; der Architekt bestätigt oder
> korrigiert sie, bevor `immo-builder` die Migration schreibt.

### 4.1 Datenmodell — empfohlene Richtung

`SEPAMandat` wird um einen **Geltungsbereich** erweitert:

```
SEPAMandat
  + person              FK(Person, PROTECT, related_name='sepa_mandate')   # Eigentümer des Mandats
  + eigentumsverhaeltnis FK(EigentumsVerhaeltnis, null=True, blank=True,   # NULL = Sammelmandat (alle Einheiten)
                            related_name='sepa_mandate')                    # gesetzt = nur diese Einheit
```

- `person` macht den Mandatseigentümer **direkt** adressierbar (heute nur
  rückwärts über `Person.sepa_mandat`). Ein Eigentümer kann damit **mehrere**
  Mandate haben → genau das, was das Feature braucht.
- `eigentumsverhaeltnis = NULL` ⇒ Sammelmandat; gesetzt ⇒ einheitenspezifisch.
- **`Person.sepa_mandat` bleibt in v1 bestehen** (Legacy-/Kompatibilitäts-FK)
  und zeigt weiter auf das **Sammelmandat**. Das Entfernen dieses Feldes ist
  **irreversibel** und braucht ausdrückliche Freigabe → **eigener HALT**, nicht
  Teil von v1.
- **Daten-Migration:** für jede `Person` mit gesetztem `sepa_mandat` →
  `mandat.person = person`, `mandat.eigentumsverhaeltnis = NULL`
  (Bestandsmandate werden zu Sammelmandaten). Idempotent, keine Löschung.

**Alternative (vom Architekten zu bewerten):** Through-Modell
`SepaMandatZuordnung(mandat, eigentumsverhaeltnis)` statt einzelner FK, falls ein
Mandat später explizit **mehrere ausgewählte** Einheiten (aber nicht alle)
abdecken soll. Für v1 (eine Einheit *oder* alle) genügt der einzelne FK; das
Through-Modell ist überdimensioniert. Architekt entscheidet.

### 4.2 Pending-Änderung + Token (Spiegel des E-Mail-Flows)

Neues Modell `PortalSepaMandatAenderung` (analog zu `email_pending` + Token):

```
PortalSepaMandatAenderung
  id, zugang FK(PortalZugang)
  geltungsbereich  CharField  # 'alle' | 'einheit'
  eigentumsverhaeltnis FK(EigentumsVerhaeltnis, null=True)  # nur bei 'einheit'
  iban, bic
  aktion           CharField  # 'anlage' | 'aenderung'
  status           CharField  # 'offen' | 'bestaetigt' | 'verfallen'
  erstellt_am, bestaetigt_am
```

Neuer `PortalToken`-Typ `TYP_SEPA_MANDAT = 'sepa_mandat'`. Der Token referenziert
den Pending-Datensatz (FK oder, minimalinvasiv, über `zugang`+`typ`+jüngsten
offenen Eintrag — Architekt entscheidet; Vorbild `ziel_email` zeigt das Muster
„Zieldaten am Token festhalten, damit ein späteres Ändern einen bereits
versandten Link nicht umlenkt", `models.py:118-121`).

### 4.3 Resolver (eine Funktion, R2)

Neuer Service `apps/buchhaltung/services/…` **oder** `apps/portal/services/…`
(Architekt legt Ort fest):

```
mandat_fuer_ev(ev) -> SEPAMandat | None
    # 1) aktives Mandat mit eigentumsverhaeltnis == ev
    # 2) sonst aktives Sammelmandat der ev.person (eigentumsverhaeltnis IS NULL)
    # 3) sonst None
```

Der Lastschrift-Einzug (`sepa_lastschrift.py:220`) ersetzt die Zeile
`mandat = person.sepa_mandat` durch `mandat = mandat_fuer_ev(ev)` und
**überspringt** EVs ohne Mandat statt mit `None` abzustürzen (heute würde
`mandat.iban` bei fehlendem Mandat eine `AttributeError` werfen — das ist ein
**Bestandsrisiko**, das dieser Umbau mitbehebt).

---

## 5. Backend — zu bauen

1. **Migration** (`immo-builder`, nach Architekt-Freigabe): Felder aus §4.1,
   Modell aus §4.2, neuer Token-Typ; Daten-Migration Bestandsmandate →
   Sammelmandate. Idempotent.
2. **Service** `sepa_mandat_service.py` (im Portal-App-Service-Ordner):
   - `stosse_mandat_an(zugang, geltungsbereich, eigentumsverhaeltnis_id, iban, bic)`
     — validiert IBAN (R5), prüft Zugehörigkeit der Einheit zum Zugang (R8),
     ermittelt `aktion` (anlage/aenderung, R4), legt `PortalSepaMandatAenderung`
     an, erzeugt Token, versendet Magic-Link-Mail. Kein Mandat wird hier schon
     geschrieben.
   - `bestaetige_mandat(token_wert)` — löst Token ein (`loese_token_ein`),
     wendet den Pending-Datensatz an: Mandat **anlegen** (inkl.
     `mandatsreferenz` generieren, `unterzeichnet_am = heute`,
     `sequence_type='FRST'`) **oder** bestehendes Mandat des Geltungsbereichs
     ändern (IBAN/BIC, `mandatsreferenz` bleibt — wie `stammdaten_service.py:171`);
     `Person.ibans` pflegen (R7); `person`/`eigentumsverhaeltnis`/`sepa_mandat`
     verknüpfen; `protokolliere(...)` (R6); Pending auf `bestaetigt`.
   - `mandatsreferenz` generieren: Architekt gibt das Schema vor (eindeutig,
     ≤ 35 Zeichen, `SEPAMandat.mandatsreferenz` ist `unique`).
3. **Endpunkte** (`apps/portal/views*.py` + `urls.py`), alle mit
   `PortalSessionAuthentication` + `IstPortalNutzer`:
   - `GET  /api/v1/portal/sepa-mandat/` — aktueller Zustand: Liste der aktiven
     Mandate des Eigentümers je Geltungsbereich + Einheitenliste für den Dialog
     (für R4-Beschriftung).
   - `POST /api/v1/portal/sepa-mandat/anfordern/` — ruft `stosse_mandat_an`.
     Neutrale Antwort (wie Magic-Link-Request, `views.py:41`).
   - `POST /api/v1/portal/sepa-mandat/bestaetigen/` — ruft `bestaetige_mandat`.
4. **Resolver + Einzug-Umbau** (§4.3) inkl. „EV ohne Mandat überspringen".
5. **E-Mail-Template** `templates/email/portal_sepa_mandat.(txt|html)` analog zu
   `portal_email_bestaetigung`.

---

## 6. Frontend — zu bauen

1. **Button in der Kopfzeile** `PortalLayout.tsx` (Header, neben der Nav): Label
   zustandsabhängig „SEPA-Lastschriftmandat" / „… ändern" (R4; Zustand aus
   `GET /sepa-mandat/`). Öffnet den Dialog.
2. **Dialog**: bei **mehreren** aktiven Einheiten Auswahl „für eine Einheit
   (Dropdown) / für alle Einheiten"; bei **einer** Einheit keine Auswahl. IBAN-
   (+optional BIC-)Eingabe mit `IbanInput`/`ibanPruefen` (bestehende
   Komponenten, siehe `MeineDaten.tsx`). Senden ruft `/anfordern/`; danach
   Hinweis „Bitte bestätigen Sie den Link in Ihrer E-Mail."
3. **Bestätigungsseite** analog `PortalEmailBestaetigen.tsx` + Route
   (z. B. `/portal/sepa-mandat/bestaetigen`), ruft `/bestaetigen/` mit dem
   Token aus der URL, zeigt Erfolg/Fehler.
4. **API-Client** `frontend/src/api/portal.ts`: `sepaMandatStatus`,
   `sepaMandatAnfordern`, `sepaMandatBestaetigen`.

Design: bestehende Portal-Tokens/Farben (`portal-brand` etc.), Mockup-Stil aus
`docs/immocore_portal_mockup.html` wahren.

---

## 7. Orchestrierungs-Modell (Fable = nur Kontrolle)

**Fable schreibt keinen Produktivcode.** Fable zerlegt jede Phase in
Teilaufgaben, wählt je Teilaufgabe den **günstigsten passenden** Subagenten,
prüft dessen Ergebnis gegen diese Spec und gibt erst dann frei.

| Subagent | Modell | Einsatz |
|---|---|---|
| `immo-explorer` | Haiku | Lesende Verifikation, Feld-/Zählabfragen, Ist-Sichtung. **Immer zuerst.** |
| `immo-builder` | Sonnet | Migration, Services, Endpunkte, Frontend, Tests. |
| `immo-architect` | Opus | **Nur** bei Urteils-/Risiko-/Rechtsfragen: Modellform (§4.1), Rechtsgültigkeit „SEPA-Mandat per Magic Link" (§8 HALT-A), `mandatsreferenz`-Schema, Token-Bindung. |

Regeln für Fable:
- Beginne jede Phase mit `immo-explorer`, eskaliere so spät wie möglich.
  Begründe jede Agenten-/Modellwahl in **einem Satz**.
- Subagenten können **nicht** weiter delegieren — gib jedem **alle** nötigen
  Infos (Dateipfade, verifizierte Feldnamen, Fehlermeldungen) direkt mit.
- An **jedem HALT** anhalten, kompakt berichten (Gemacht / Testergebnis /
  Offenes), **nicht** eigenständig darüber hinaus.
- Irreversible/finanzwirksame Schritte (Entfernen von `Person.sepa_mandat`,
  Daten-Migration) **nie** ohne ausdrückliche Freigabe des Nutzers.

Bericht nach jeder Phase: welche Teilaufgabe an welchen Subagenten (+
Begründung), Prüfergebnis je Teilaufgabe (bestanden/nachgebessert),
Testergebnisse, offene Punkte, Abschluss „HALT – warte auf Freigabe" oder
„bereit für nächste Phase".

---

## 8. Phasenplan mit HALT-Punkten

### Phase 0 — Ist-Verifikation (`immo-explorer`)
Bestätige §0 am laufenden Code und ergänze, was §0 nicht abdeckt:
- V1 Feldliste `SEPAMandat`, `Person` (Mandats-/IBAN-Felder) — exakt.
- V2 Alle Lesestellen von `Person.sepa_mandat` im Produktivcode.
- V3 Token-/Mail-/Bestätigungs-Flow der E-Mail-Änderung — Funktionssignaturen.
- V4 Frontend: Header-Aufbau `PortalLayout.tsx`, `PortalEmailBestaetigen.tsx`,
  `api/portal.ts`-Muster, Einheiten-Abfrage.
- V5 Wo/wie `EigentumsVerhaeltnis` „aktiv je Einheit" bestimmt wird.
**Akzeptanz:** Feldnamen & Signaturen schriftlich fixiert.
**HALT 0:** Fable legt die Befunde vor. → Freigabe, dann Feldnamen der Spec an
Ist angleichen.

### Phase 1 — Architektur-Entscheid (`immo-architect`) — **HALT-A**
Entscheide verbindlich: (a) Datenmodell §4.1 (Einzel-FK vs. Through-Modell;
`Person.sepa_mandat` in v1 behalten); (b) Rechtsgültigkeit „SEPA-Mandat per
Magic-Link bestätigt" inkl. zu protokollierender Felder (Zeitstempel, ggf. IP,
Quelle); (c) `mandatsreferenz`-Schema; (d) Ort/Signatur des Resolvers §4.3; (e)
Token↔Pending-Bindung §4.2.
**Akzeptanz:** schriftliche Festlegung je Punkt mit Begründung.
**HALT-A:** Nutzer-Freigabe, bevor irgendeine Migration geschrieben wird.

### Phase 2 — Datenmodell & Migration (`immo-builder`)
Felder/Modell/Token-Typ + idempotente Daten-Migration (Bestandsmandate →
Sammelmandate).
**Akzeptanz:** `makemigrations --check` sauber; Migration vorwärts **und**
rückwärts in leerer Test-DB lauffähig; bestehende Mandate behalten Verhalten.
**HALT 2** vor Anwendung auf Daten mit Bestand.

### Phase 3 — Resolver & Einzug-Umbau (`immo-builder`)
`mandat_fuer_ev` + Umbau `sepa_lastschrift.py` (EV ohne Mandat überspringen).
**Akzeptanz:** neue Unit-Tests (einheitenspezifisch schlägt Sammelmandat;
Sammelmandat greift; kein Mandat → kein Einzug, kein Crash); bestehende
Lastschrift-Tests grün (`apps/buchhaltung/tests/test_lastschrift_*`).

### Phase 4 — Service & Endpunkte + Magic-Link (`immo-builder`)
`sepa_mandat_service` (anstoßen/bestätigen), 3 Endpunkte, E-Mail-Template.
**Akzeptanz:** Tests für Anlage- und Änderungs-Flow je Geltungsbereich; ungültiger/
verbrauchter/abgelaufener Token wird abgewiesen; Isolation (R8) getestet; Audit-
Eintrag (R6) entsteht.

### Phase 5 — Frontend (`immo-builder`)
Button (R4), Dialog (Einheit/alle), Bestätigungsseite + Route, API-Client.
**Akzeptanz:** Button-Label zustandsabhängig; Dialog verbirgt Auswahl bei einer
Einheit; End-to-End im Dev-Stack klickbar (Anfordern → Mail-Link → Bestätigen →
Mandat aktiv).

### Phase 6 — Abnahme (`immo-explorer` liest gegen, Fable prüft)
Smoke-Test gegen alle Regeln R1–R8, Testlauf gesamt.
**HALT 6:** Schlussbericht an Nutzer.

---

## 9. Tests (Minimum)

- Resolver-Rangfolge (R2) in allen drei Fällen.
- Einzug zieht je Einheit das richtige Mandat; EV ohne Mandat wird übersprungen.
- Anlage-Flow: offen → Magic-Link → bestätigt; Mandat mit korrektem
  Geltungsbereich, `mandatsreferenz` eindeutig, `unterzeichnet_am` gesetzt.
- Änderungs-Flow: IBAN/BIC geändert, `mandatsreferenz` unverändert, alte IBAN in
  `Person.ibans` erhalten (R7).
- Token ungültig/verbraucht/abgelaufen → abgewiesen, kein Mandat geändert.
- Isolation (R8): fremde `eigentumsverhaeltnis_id` wird nicht akzeptiert.
- Button-Label „erteilen" vs. „ändern" je Zustand.

---

## 10. Offene Punkte / Risiken

- **Bestandsrisiko (vorab):** `sepa_lastschrift.py:220` würde bei einer Person
  **ohne** Mandat heute `mandat.iban` auf `None` aufrufen → `AttributeError`.
  Der Umbau in Phase 3 behebt das mit; bitte in Phase 0 bestätigen, ob dieser
  Fall heute praktisch vorkommen kann.
- **Rechtsgültigkeit** des per Magic Link erteilten SEPA-Mandats ist eine
  fachlich-rechtliche Frage (HALT-A) — hier wird die technische Protokollierung
  geliefert, nicht die rechtliche Bewertung.
- **`Person.sepa_mandat` entfernen** ist bewusst **nicht** v1 (irreversibel).
- **Mandats-Widerruf** durch den Eigentümer ist out of scope — klären, ob als
  v1.1 gewünscht.

---

*Diese Anleitung ist als Orchestrator-Prompt für eine Fable-5-Session gedacht:
Fable startet mit Phase 0 und schlägt zuerst die Agenten-/Modellzuordnung für
die V1–V5-Erhebung vor, bevor der erste Subagent aufgerufen wird.*
