# IMMOCORE — Projektstand (Code-Status)

| | |
|---|---|
| **Export-Zeitpunkt** | 2026-08-19 |
| **Git-Branch** | `main` |
| **Git-HEAD** | `3fb630d` — *fix(handwerker): Auftragsversand verweigern, wenn in Produktion kein SMTP konfiguriert ist* |
| **Remote-Stand** | `origin/main` = `3fb630d` (synchron) |
| **Live-Server** | 87.106.219.148, deployt auf Stand `3fb630d` |
| **Testsuite** | 718 Tests, alle grün |
| **Django-Apps** | 13 Projekt-Apps unter `backend/apps/` |
| **Modelle** | 87 |
| **Migrationen** | 180, davon 0 offen — lokal und produktiv identisch |

## Hinweise zur Erhebung

- **Abweichung zur Aufgabenstellung:** Es gibt kein monolithisches
  `immocore/models.py`, `immocore/admin.py` oder
  `immocore/management/commands/`. Das Projekt ist nach Django-Apps unter
  `backend/apps/` aufgeteilt; alle Abschnitte sind entsprechend je App
  gegliedert.
- Abschnitte 1, 4, 5, 7 und 8 wurden per **Django-Introspektion aus der
  laufenden Konfiguration** erzeugt (`django.apps`, `admin.site._registry`,
  URL-Resolver, `settings`), nicht aus dem Quelltext abgeschrieben. Sie geben
  damit exakt den geladenen Code-Stand wieder.
- Abschnitt 2 enthält den Migrationsstand der **produktiven** Datenbank.
- Abschnitt 6 wurde direkt aus den Excel-Dateien gelesen.
- Abschnitt 3 (Modul-Matrix) ist die einzige Sektion mit Bewertung; sie stützt
  sich auf vorhandene Modelle, Services und Specs. Nicht belegbare Angaben sind
  als solche gekennzeichnet.

---

## 1. Datenmodell (Django-Modelle)

Ausgelesen per Django-Introspektion aus der laufenden Konfiguration (`django.apps`), nicht aus dem Quelltext — entspricht damit exakt dem geladenen Stand. Das Projekt hat **kein** monolithisches `models.py`, sondern ist nach Apps unter `backend/apps/` aufgeteilt.

### 1.0 Übersicht

| App | Modelle | Anzahl |
|---|---|---|
| `abrechnung_wp` | `Wirtschaftsplan`, `WirtschaftsplanAnteil`, `WirtschaftsplanPosition` | 3 |
| `buchhaltung` | `AutoLaufProtokoll`, `BankErkennungsLog`, `BankImport`, `BankMatchRegel`, `Basiszinssatz`, `Buchung`, `Buchungsart`, `Buchungsstapel`, `CamtImportEinstellung`, `CamtImportLog`, `EigentuemerwechselVorgang`, `EinzelAbrechnung`, `Forderungsfall`, `FrontofficeAufgabe`, `HausgeldSollstellung`, `HausgeldSollstellungslauf`, `ImportOrdnerEinstellung`, `Jahresabrechnung`, `Kontoumsatz`, `KreditorOP`, `LastschriftLauf`, `Mahnlauf`, `Mahnsperre`, `Mahnung`, `OffenerPosten`, `OposSequenz`, `RAPAufloesung`, `RAPPosition`, `SepaZahlungslauf`, `SollstellungSplit`, `SollstellungZahlung`, `WechselKorrekturPaar`, `WiederkehrendeBuchungOP`, `WiederkehrendeBuchungSplit`, `WiederkehrendeBuchungVorlage`, `WirtschaftsplanBeschluss`, `WirtschaftsplanKorrekturPaar`, `WirtschaftsplanPosition`, `WirtschaftsplanRuecklage` | 39 |
| `dokumente` | `BelegnummerZaehler`, `Dokument` | 2 |
| `handwerker` | `AuftragsbestaetigungsToken`, `Gewerk`, `Handwerkerauftrag`, `HandwerkerauftragEreignis`, `HandwerkerauftragNummerZaehler`, `ObjektHandwerker` | 6 |
| `konten` | `Abrechnungsart`, `Konto`, `KontoVerteilerSchluessel`, `Personenkonto`, `Unterkonto` | 5 |
| `massenimport` | `ImportJob` | 1 |
| `mitarbeiter` | `Mitarbeiter`, `MitarbeiterObjektZuordnung` | 2 |
| `objekte` | `Bankkonto`, `Eingang`, `Einheit`, `EinheitVerbrauch`, `Objekt`, `Verteilerschluessel`, `VerteilerschluesselWert`, `Wirtschaftsjahr` | 8 |
| `personen` | `EigentumsVerhaeltnis`, `HausgeldHistorie`, `Mietvertrag`, `Person`, `SEPAMandat` | 5 |
| `prozesse` | `Prozess` | 1 |
| `rechnungen` | `Freigabe`, `FreigabelimitDefault`, `Kreditor`, `KreditorRegel`, `Rechnung`, `RechnungSplitPosition`, `RechnungsBearbeitungsLock`, `RechnungsErkennungsLog`, `RechnungsMatchRegel`, `Verarbeitungslog` | 10 |
| `vorgaenge` | `Vorgang`, `VorgangAntwortVorschlag`, `VorgangEreignis`, `VorgangNummerZaehler`, `VorgangTyp` | 5 |

**Gesamt: 87 Modelle in 12 Apps.**

### 1.1 App `abrechnung_wp`

#### `Wirtschaftsplan`

- **Tabelle:** `abrechnung_wp_wirtschaftsplan`
- **Bezeichnung:** Wirtschaftsplan / Wirtschaftspläne

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wirtschaftsjahr` | ForeignKey | — | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=CASCADE; related_name=`wirtschaftsplaene` |
| `status` | CharField | — | `'entwurf'` | max_length=12; choices: `entwurf`, `beschlossen`, `aktiv`, `aufgehoben` |
| `gesamtsumme` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `gesamtsumme_hausgeld` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `gesamtsumme_ruecklage` | JSONField | — | `dict()` | — |
| `beschluss_datum` | DateField | null/blank | — | — |
| `beschluss_tagesordnungspunkt` | CharField | null/blank | — | max_length=100 |
| `wirkung_ab` | DateField | — | — | — |
| `bemerkung` | TextField | null/blank | — | — |
| `aufhebt_wp` | ForeignKey | null/blank | — | db_index; → `abrechnung_wp.Wirtschaftsplan`; on_delete=PROTECT; related_name=`abgeloest_durch` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_wirtschaftsplaene` |
| `beschlossen_am` | DateTimeField | null/blank | — | — |
| `beschlossen_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`beschlossene_wirtschaftsplaene` |

**Meta:**
- `ordering = ['-wirtschaftsjahr__jahr', 'status']`
- `UniqueConstraint(['wirtschaftsjahr', 'status'], name='uniq_wp_wj_aktiv_beschlossen')` condition=(AND: ('status__in', ['beschlossen', 'aktiv']))

#### `WirtschaftsplanAnteil`

- **Tabelle:** `abrechnung_wp_wirtschaftsplananteil`
- **Bezeichnung:** Wirtschaftsplan-Anteil / Wirtschaftsplan-Anteile

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `position` | ForeignKey | — | — | db_index; → `abrechnung_wp.WirtschaftsplanPosition`; on_delete=CASCADE; related_name=`anteile` |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=PROTECT; related_name=`wp_anteile` |
| `vs_anteil_einheit` | DecimalField | — | — | max_digits=18, decimal_places=6 |
| `vs_anteil_gesamt` | DecimalField | — | — | max_digits=18, decimal_places=6 |
| `betrag_anteil` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `monatsbetrag_anteil` | DecimalField | — | — | max_digits=12, decimal_places=2 |

**Meta:**
- `ordering = ['einheit__einheit_nr']`
- `UniqueConstraint(['position', 'einheit'], name='uniq_wp_anteil_position_einheit')`

#### `WirtschaftsplanPosition`

- **Tabelle:** `abrechnung_wp_wirtschaftsplanposition`
- **Bezeichnung:** Wirtschaftsplan-Position / Wirtschaftsplan-Positionen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wirtschaftsplan` | ForeignKey | — | — | db_index; → `abrechnung_wp.Wirtschaftsplan`; on_delete=CASCADE; related_name=`positionen` |
| `konto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`wp_positionen` |
| `vs_code` | CharField | — | — | max_length=3 |
| `betrag` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `verteilung_validiert` | BooleanField | — | `False` | — |
| `verteilung_freigegeben_trotz_diff` | BooleanField | — | `False` | — |
| `bemerkung` | CharField | null/blank | — | max_length=255 |

**Meta:**
- `ordering = ['konto__kontonummer']`
- `UniqueConstraint(['wirtschaftsplan', 'konto'], name='uniq_wp_position_wp_konto')`
- `CheckConstraint(name='wp_position_betrag_nicht_negativ')`

### 1.2 App `buchhaltung`

#### `AutoLaufProtokoll`

- **Tabelle:** `buchhaltung_autolaufprotokoll`
- **Bezeichnung:** Auto-Lauf-Protokoll / Auto-Lauf-Protokolle

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`auto_lauf_protokolle` |
| `ausgefuehrt_am` | DateTimeField | — | — | — |
| `periode` | DateField | — | — | — |
| `status` | CharField | — | — | max_length=20; choices: `erfolg`, `teilweise_erfolg`, `fehler`, `uebersprungen` |
| `sollstellungslauf` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellungslauf`; on_delete=PROTECT; related_name=`auto_lauf_protokolle` |
| `lastschriftlauf` | ForeignKey | null/blank | — | db_index; → `buchhaltung.LastschriftLauf`; on_delete=PROTECT; related_name=`auto_lauf_protokolle` |
| `anzahl_evs_geplant` | IntegerField | — | `0` | — |
| `anzahl_evs_erfolgreich` | IntegerField | — | `0` | — |
| `anzahl_evs_uebersprungen` | IntegerField | — | `0` | — |
| `summe_sollstellungen` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `summe_lastschrift` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `datei_pfad` | CharField | null/blank | — | max_length=500 |
| `warnungen` | JSONField | blank | `list()` | — |
| `fehler` | TextField | null/blank | — | — |

**Meta:**
- `ordering = ['-ausgefuehrt_am']`

#### `BankErkennungsLog`

- **Tabelle:** `buchhaltung_bankerkennungslog`
- **Bezeichnung:** Bank-Erkennungs-Log / Bank-Erkennungs-Logs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `kontoumsatz` | ForeignKey | — | — | db_index; → `buchhaltung.Kontoumsatz`; on_delete=CASCADE; related_name=`erkennungs_logs` |
| `stufe_erreicht` | CharField | — | — | max_length=3 |
| `quelle` | CharField | blank | — | max_length=20; choices: `e2e_id`, `iban_ev`, `bank_match_regel`, `iban_kreditor`, `ki`, `keine` |
| `konfidenz` | DecimalField | null/blank | — | max_digits=3, decimal_places=2 |
| `gegenkonto_vorschlag` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=SET_NULL; related_name=`bank_erkennungs_logs` |
| `regel_treffer` | ForeignKey | null/blank | — | db_index; → `buchhaltung.BankMatchRegel`; on_delete=SET_NULL; related_name=`erkennungs_logs` |
| `auto_verbucht` | BooleanField | — | `False` | — |
| `details_json` | JSONField | null/blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `BankImport`

- **Tabelle:** `buchhaltung_bankimport`
- **Bezeichnung:** Bank-Import (Legacy) / Bank-Importe (Legacy)

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`bank_importe` |
| `sha256_hash` | CharField | — | — | max_length=64; unique |
| `auftraggeber_name` | CharField | blank | — | max_length=255 |
| `auftraggeber_iban` | CharField | blank | — | max_length=34 |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `buchungsdatum` | DateField | — | — | — |
| `wertstellungsdatum` | DateField | null/blank | — | — |
| `verwendungszweck` | TextField | blank | — | — |
| `status` | CharField | — | `'neu'` | max_length=20; choices: `neu`, `erkannt`, `manuell`, `ignoriert` |
| `buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`bank_importe` |
| `ki_vorschlag` | JSONField | null/blank | — | — |
| `importiert_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-buchungsdatum', '-importiert_am']`

#### `BankMatchRegel`

- **Tabelle:** `buchhaltung_bankmatchregel`
- **Bezeichnung:** Bank-Match-Regel / Bank-Match-Regeln

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `bankkonto` | ForeignKey | — | — | db_index; → `objekte.Bankkonto`; on_delete=CASCADE; related_name=`match_regeln` |
| `kontrahent_iban` | CharField | — | — | max_length=34 |
| `verwendungszweck_hash` | CharField | — | — | max_length=64 |
| `gegenkonto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`bank_match_regeln` |
| `kreditor` | ForeignKey | null/blank | — | db_index; → `personen.Person`; on_delete=SET_NULL; related_name=`bank_match_regeln` |
| `eigentumsverhaeltnis` | ForeignKey | null/blank | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=SET_NULL; related_name=`bank_match_regeln` |
| `status` | CharField | — | `'aktiv'` | max_length=10; choices: `aktiv`, `veraltet` |
| `erstellt_aus` | CharField | — | — | max_length=15; choices: `bestaetigung`, `korrektur`, `manuell` |
| `trefferzahl` | IntegerField | — | `0` | — |
| `letzte_anwendung` | DateTimeField | null/blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_bank_match_regeln` |

**Meta:**
- `ordering = ['-trefferzahl', '-letzte_anwendung']`
- `UniqueConstraint(['bankkonto', 'kontrahent_iban', 'verwendungszweck_hash'], name='unique_aktive_bankregel')` condition=(AND: ('status', 'aktiv'))

#### `Basiszinssatz`

- **Tabelle:** `buchhaltung_basiszinssatz`
- **Bezeichnung:** Basiszinssatz / Basiszinssätze

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `gueltig_ab` | DateField | — | — | unique |
| `satz` | DecimalField | — | — | max_digits=5, decimal_places=2 |
| `quelle` | CharField | blank | — | max_length=255 |

**Meta:**
- `ordering = ['-gueltig_ab']`

#### `Buchung`

- **Tabelle:** `buchhaltung_buchung`
- **Bezeichnung:** Buchung / Buchungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`buchungen` |
| `buchungsart` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchungsart`; on_delete=PROTECT; related_name=`buchungen` |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `soll_konto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`soll_buchungen` |
| `haben_konto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`haben_buchungen` |
| `soll_unterkonto` | ForeignKey | null/blank | — | db_index; → `konten.Unterkonto`; on_delete=SET_NULL; related_name=`soll_buchungen` |
| `unterkonto` | ForeignKey | null/blank | — | db_index; → `konten.Unterkonto`; on_delete=SET_NULL; related_name=`buchungen` |
| `personenkonto` | ForeignKey | null/blank | — | db_index; → `konten.Personenkonto`; on_delete=SET_NULL; related_name=`hauptbuchungen` |
| `kreditor` | ForeignKey | null/blank | — | db_index; → `rechnungen.Kreditor`; on_delete=SET_NULL; related_name=`buchungen` |
| `parent_buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=CASCADE; related_name=`teilbuchungen` |
| `belegnr` | CharField | blank | — | max_length=50 |
| `buchungsdatum` | DateField | — | — | — |
| `belegdatum` | DateField | null/blank | — | — |
| `wertstellungsdatum` | DateField | null/blank | — | — |
| `buchungstext` | TextField | blank | — | — |
| `verwendungszweck` | TextField | blank | — | — |
| `wirtschaftsjahr_nr` | IntegerField | null/blank | — | — |
| `wirtschaftsjahr` | ForeignKey | null/blank | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=PROTECT; related_name=`buchungen_wj` |
| `kostenstelle` | CharField | blank | — | max_length=20 |
| `beleg_referenz` | CharField | blank | — | max_length=255 |
| `storno_von` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`stornobuchungen` |
| `status` | CharField | — | `'entwurf'` | max_length=20; choices: `entwurf`, `festgeschrieben`, `storniert` |
| `stapel` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchungsstapel`; on_delete=SET_NULL; related_name=`buchungen` |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`buchungen` |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-buchungsdatum', '-erstellt_am']`

#### `Buchungsart`

- **Tabelle:** `buchhaltung_buchungsart`
- **Bezeichnung:** Buchungsart / Buchungsarten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `nr` | CharField | — | — | max_length=3; unique |
| `kuerzel` | CharField | — | — | max_length=12 |
| `bezeichnung` | CharField | — | — | max_length=120 |
| `einzelabrechnung` | CharField | — | `'nein'` | max_length=12; choices: `ja`, `nein`, `anteilig` |
| `gesamtabrechnung` | BooleanField | — | `False` | — |
| `ruecklagen_relevant` | BooleanField | — | `False` | — |
| `umlage` | CharField | — | `'gesperrt'` | max_length=12; choices: `pflicht`, `optional`, `gesperrt` |
| `beleg_pflicht` | BooleanField | — | `True` | — |
| `beschluss_pflicht` | BooleanField | — | `False` | — |
| `vier_augen_schwelle` | DecimalField | null/blank | — | max_digits=12, decimal_places=2 |
| `sperre_nach_jahresabschluss` | BooleanField | — | `True` | — |
| `system_buchungsart` | BooleanField | — | `False` | — |
| `default_konto_soll_pattern` | CharField | blank | — | max_length=20 |
| `default_konto_haben_pattern` | CharField | blank | — | max_length=20 |
| `aktiv` | BooleanField | — | `True` | — |
| `tilgungs_prioritaet` | IntegerField | null/blank | — | — |
| `erloeskonto_default_nr` | CharField | blank | — | max_length=10 |
| `bankkonto_typ` | CharField | null/blank | — | max_length=25; choices: `bewirtschaftung`, `ruecklage_nach_index`, `frei` |
| `buchungstyp` | CharField | null/blank | — | max_length=20; choices: `sachkonto`, `personenkonto`, `kreditor` |
| `richtung` | CharField | null/blank | — | max_length=10; choices: `eingang`, `abgang` |

**Meta:**
- `ordering = ['nr']`

#### `Buchungsstapel`

- **Tabelle:** `buchhaltung_buchungsstapel`
- **Bezeichnung:** Buchungsstapel / Buchungsstapel

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`buchungsstapel` |
| `bezeichnung` | CharField | blank | — | max_length=120 |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `ausgebucht` |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`buchungsstapel` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `ausgebucht_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`ausgebuchte_stapel` |
| `ausgebucht_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `CamtImportEinstellung`

- **Tabelle:** `buchhaltung_camtimporteinstellung`
- **Bezeichnung:** CAMT-Import-Einstellung / CAMT-Import-Einstellungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=SET_NULL; related_name=`camt_einstellungen` |
| `import_ordner` | CharField | blank | — | max_length=500 |
| `archiv_ordner` | CharField | blank | — | max_length=500 |
| `fehler_ordner` | CharField | blank | — | max_length=500 |
| `poll_intervall_sek` | IntegerField | — | `30` | — |
| `datei_muster` | CharField | — | `'*.xml,*.camt'` | max_length=200 |
| `aktiv` | BooleanField | — | `True` | — |
| `zuletzt_geprueft_am` | DateTimeField | null/blank | — | — |
| `letzter_import_am` | DateTimeField | null/blank | — | — |
| `letzter_import_datei` | CharField | blank | — | max_length=500 |

#### `CamtImportLog`

- **Tabelle:** `buchhaltung_camtimportlog`
- **Bezeichnung:** CAMT-Import-Log / CAMT-Import-Logs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `einstellung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.CamtImportEinstellung`; on_delete=CASCADE; related_name=`logs` |
| `zeitpunkt` | DateTimeField | blank | — | — |
| `import_ordner` | CharField | blank | — | max_length=500 |
| `anzahl_dateien` | IntegerField | — | `0` | — |
| `anzahl_importiert` | IntegerField | — | `0` | — |
| `anzahl_duplikate` | IntegerField | — | `0` | — |
| `anzahl_erkannt` | IntegerField | — | `0` | — |
| `anzahl_fehler` | IntegerField | — | `0` | — |
| `fehler_details` | JSONField | blank | `list()` | — |
| `typ` | CharField | — | `'camt053'` | max_length=8; choices: `camt053`, `camt054` |
| `status` | CharField | — | `'ok'` | max_length=30; choices: `ok`, `pending_mahnwesen_spec`, `fehler` |
| `notiz` | TextField | blank | — | — |

**Meta:**
- `ordering = ['-zeitpunkt']`

#### `EigentuemerwechselVorgang`

- **Tabelle:** `buchhaltung_eigentuemerwechselvorgang`
- **Bezeichnung:** Eigentümerwechsel-Vorgang / Eigentümerwechsel-Vorgänge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`eigentuemerwechsel_vorgaenge` |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=PROTECT; related_name=`eigentuemerwechsel_vorgaenge` |
| `voreigentuemer_ev` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`eigentuemerwechsel_als_voreigentuemer` |
| `neueigentuemer_ev` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`eigentuemerwechsel_als_neueigentuemer` |
| `wechsel_datum` | DateField | — | — | — |
| `meldedatum` | DateField | — | — | — |
| `status` | CharField | — | `'vorschau'` | max_length=20; choices: `vorschau`, `freigegeben` |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_eigentuemerwechsel` |
| `freigegeben_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`freigegebene_eigentuemerwechsel` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `freigegeben_am` | DateTimeField | null/blank | — | — |
| `auszahlungsbetrag` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `auszahlungs_iban` | CharField | blank | — | max_length=34 |
| `notiz` | TextField | null/blank | — | — |
| `auszahlung_unterdruecken` | BooleanField | — | `False` | — |

**Meta:**
- `ordering = ['-erstellt_am']`
- `CheckConstraint(name='ev_vorgang_vier_augen')`

#### `EinzelAbrechnung`

- **Tabelle:** `buchhaltung_einzelabrechnung`
- **Bezeichnung:** Einzelabrechnung / Einzelabrechnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `jahresabrechnung` | ForeignKey | — | — | db_index; → `buchhaltung.Jahresabrechnung`; on_delete=CASCADE; related_name=`einzelabrechnungen` |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=PROTECT; related_name=`einzelabrechnungen` |
| `eigentuemer` | ForeignKey | — | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`einzelabrechnungen` |
| `eigentumsverhaeltnis` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`einzelabrechnungen` |
| `hausgeld_soll_gesamt` | DecimalField | — | — | max_digits=14, decimal_places=2 |
| `kostenanteil_gesamt` | DecimalField | — | — | max_digits=14, decimal_places=2 |
| `ruecklagen_zufuehrung_gesamt` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `abrechnungsergebnis` | DecimalField | — | — | max_digits=14, decimal_places=2 |
| `positionen` | JSONField | — | `list()` | — |
| `ruecklagen` | JSONField | — | `list()` | — |
| `sollstellung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=SET_NULL; related_name=`einzelabrechnungen` |
| `dokument` | ForeignKey | null/blank | — | db_index; → `dokumente.Dokument`; on_delete=SET_NULL; related_name=`einzelabrechnungen` |
| `hinweis_eigentuemerwechsel` | BooleanField | — | `False` | — |

**Meta:**
- `ordering = ['jahresabrechnung', 'einheit__einheit_nr']`
- `UniqueConstraint(['jahresabrechnung', 'einheit'], name='einzelabrechnung_unique_je_einheit')`

#### `Forderungsfall`

- **Tabelle:** `buchhaltung_forderungsfall`
- **Bezeichnung:** Forderungsfall / Forderungsfälle

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `personenkonto` | ForeignKey | — | — | db_index; → `konten.Personenkonto`; on_delete=PROTECT; related_name=`forderungsfaelle` |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`forderungsfaelle` |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `aussergerichtlich`, `gerichtlich`, `titulierung`, `vollstreckung`, `erfolgreich`, `uneinbringlich`, `abschreibung` |
| `eroeffnet_am` | DateField | blank | — | — |
| `eroeffnet_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`eroeffnete_forderungsfaelle` |
| `hauptforderung` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `mahngebuehren` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `verzugszinsen` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `anwaltskosten` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `gerichtskosten` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `gv_kosten` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `beschluss_referenz` | CharField | blank | — | max_length=255 |
| `notizen` | TextField | blank | — | — |
| `abgeschlossen_am` | DateField | null/blank | — | — |

**Meta:**
- `ordering = ['-eroeffnet_am']`

#### `FrontofficeAufgabe`

- **Tabelle:** `buchhaltung_frontofficeaufgabe`
- **Bezeichnung:** Frontoffice-Aufgabe / Frontoffice-Aufgaben

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`frontoffice_aufgaben` |
| `aufgabe_typ` | CharField | — | — | max_length=40; choices: `kein_sepa_mandat`, `keine_iban`, `keine_hausgeldhistorie`, `mandat_typ_frst`, `sepa_frist_unterschritten`, `dateischreibfehler`, `eigentuemerwechsel_forderung`, `saldenmitteilung_wirtschaftsplan`, `stundung_laeuft_ab` |
| `beschreibung` | TextField | — | — | — |
| `ev_id` | UUIDField | null/blank | — | max_length=32 |
| `einheit_nr` | CharField | blank | — | max_length=20 |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `in_bearbeitung`, `erledigt` |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_frontoffice_aufgaben` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erledigt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`erledigte_frontoffice_aufgaben` |
| `erledigt_am` | DateTimeField | null/blank | — | — |
| `lock_user` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`frontoffice_locks` |
| `lock_expires_at` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `HausgeldSollstellung`

- **Tabelle:** `buchhaltung_hausgeldsollstellung`
- **Bezeichnung:** Hausgeld-Sollstellung / Hausgeld-Sollstellungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`hausgeld_sollstellungen` |
| `eigentumsverhaeltnis` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`sollstellungen` |
| `sollstellungs_typ` | CharField | — | — | max_length=20; choices: `hausgeld`, `sonderumlage`, `abrechnungsergebnis`, `korrektur`, `saldovortrag` |
| `ba` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchungsart`; on_delete=PROTECT; related_name=`+` |
| `periode` | DateField | — | — | — |
| `faellig_am` | DateField | — | — | — |
| `opos_nr` | CharField | — | — | max_length=15; unique |
| `soll_betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `ist_betrag` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `status_cached` | CharField | — | `'offen'` | max_length=20; db_index |
| `sollstellungslauf` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellungslauf`; on_delete=PROTECT; related_name=`sollstellungen` |
| `storniert_am` | DateTimeField | null/blank | — | — |
| `storniert_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`+` |
| `storniert_grund` | TextField | blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`+` |
| `korrektur_grund` | CharField | null/blank | — | max_length=40; choices: `eigentuemerwechsel`, `wirtschaftsplan_aenderung` |
| `korrektur_vorgang_id` | UUIDField | null/blank | — | max_length=32 |
| `neutralisiert_durch_opos` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`+` |
| `neutralisiert_opos_nr` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`+` |
| `mahnkarenz_bis` | DateField | null/blank | — | — |
| `nachhol_aus_wp_id` | UUIDField | null/blank | — | max_length=32; db_index |

**Meta:**
- `ordering = ['-periode', 'eigentumsverhaeltnis']`
- `UniqueConstraint(['eigentumsverhaeltnis', 'periode', 'sollstellungs_typ', 'ba'], name='uniq_sollstellung_ev_periode_typ_ba')`
- `CheckConstraint(name='negative_betrag_nur_korrektur')`
- `CheckConstraint(name='korrektur_grund_consistency')`
- `Index(['objekt', 'status_cached'], name='idx_hg_ss_objekt_status')`
- `Index(['opos_nr'], name='idx_hg_ss_opos_nr')`
- `Index(['neutralisiert_durch_opos'], name='idx_hg_ss_neutralisiert')`
- `Index(['sollstellungs_typ'], name='idx_hg_ss_typ')`
- `Index(['korrektur_vorgang_id'], name='idx_hg_ss_korrektur_vorgang')`

#### `HausgeldSollstellungslauf`

- **Tabelle:** `buchhaltung_hausgeldsollstellungslauf`
- **Bezeichnung:** Hausgeld-Sollstellungslauf / Hausgeld-Sollstellungsläufe

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`hausgeld_laeufe` |
| `wirtschaftsjahr` | ForeignKey | null/blank | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=PROTECT; related_name=`hausgeld_laeufe` |
| `typ` | CharField | — | — | max_length=30; choices: `hausgeld_monat`, `sonderumlage`, `abrechnungsergebnis_jahr` |
| `periode` | DateField | — | — | — |
| `status` | CharField | — | `'vorschau'` | max_length=20; choices: `vorschau`, `freigegeben`, `commited`, `storniert` |
| `anzahl_sollstellungen` | IntegerField | — | `0` | — |
| `summe` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `fehler_details` | JSONField | blank | `list()` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`+` |
| `freigabe_user` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`freigegebene_hausgeld_laeufe` |
| `freigegeben_am` | DateTimeField | null/blank | — | — |
| `commited_am` | DateTimeField | null/blank | — | — |
| `commited_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`+` |
| `storniert_am` | DateTimeField | null/blank | — | — |
| `storniert_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`+` |
| `storniert_grund` | TextField | blank | — | — |
| `lauf_quelle` | CharField | — | `'manuell'` | max_length=10; choices: `manuell`, `autopilot` |

**Meta:**
- `ordering = ['-periode', 'objekt']`
- `UniqueConstraint(['objekt', 'periode'], name='unique_commited_lauf_pro_objekt_periode')` condition=(AND: ('status', 'commited'))

#### `ImportOrdnerEinstellung`

- **Tabelle:** `buchhaltung_importordnereinstellung`
- **Bezeichnung:** Import-Ordner-Einstellung / Import-Ordner-Einstellungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `bereich` | CharField | — | — | max_length=50; choices: `rechnungen`, `dokumente`; unique |
| `import_ordner` | CharField | blank | — | max_length=500 |
| `archiv_ordner` | CharField | blank | — | max_length=500 |
| `fehler_ordner` | CharField | blank | — | max_length=500 |
| `aktiv` | BooleanField | — | `True` | — |

#### `Jahresabrechnung`

- **Tabelle:** `buchhaltung_jahresabrechnung`
- **Bezeichnung:** Jahresabrechnung / Jahresabrechnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`jahresabrechnungen` |
| `wirtschaftsjahr` | ForeignKey | — | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=PROTECT; related_name=`jahresabrechnungen` |
| `erstellungsdatum` | DateField | blank | — | — |
| `status` | CharField | — | `'entwurf'` | max_length=20; choices: `entwurf`, `freigegeben`, `gesperrt` |
| `prozess` | ForeignKey | — | — | db_index; → `prozesse.Prozess`; on_delete=PROTECT; related_name=`jahresabrechnungen` |
| `freigegeben_am` | DateTimeField | null/blank | — | — |
| `freigegeben_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`freigegebene_jahresabrechnungen` |
| `sollstellungslauf` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellungslauf`; on_delete=SET_NULL; related_name=`jahresabrechnungen` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`jahresabrechnungen` |

**Meta:**
- `ordering = ['-wirtschaftsjahr']`
- `UniqueConstraint(['objekt', 'wirtschaftsjahr'], name='jahresabrechnung_unique_je_wj')` condition=(NOT (AND: ('status', 'storniert')))

#### `Kontoumsatz`

- **Tabelle:** `buchhaltung_kontoumsatz`
- **Bezeichnung:** Kontoumsatz / Kontoumsätze

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`kontoumsaetze` |
| `bankkonto` | ForeignKey | null/blank | — | db_index; → `objekte.Bankkonto`; on_delete=SET_NULL; related_name=`kontoumsaetze` |
| `sha256_hash` | CharField | — | — | max_length=64; unique |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `buchungsdatum` | DateField | — | — | — |
| `wertstellungsdatum` | DateField | null/blank | — | — |
| `auftraggeber_name` | CharField | blank | — | max_length=255 |
| `auftraggeber_iban` | CharField | blank | — | max_length=34 |
| `empfaenger_iban` | CharField | blank | — | max_length=34 |
| `verwendungszweck` | TextField | blank | — | — |
| `end_to_end_id` | CharField | blank | — | max_length=35 |
| `status` | CharField | — | `'importiert'` | max_length=12; choices: `importiert`, `erkannt`, `vorschlag`, `unklar`, `verbucht`, `storniert`, `manuell`, `gebucht`, `ignoriert`, `unbekannt` |
| `buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`kontoumsaetze` |
| `erkannt_gegenkonto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=SET_NULL; related_name=`kontoumsatz_gegenkonto` |
| `erkannt_eigentumsverhaeltnis` | ForeignKey | null/blank | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=SET_NULL; related_name=`kontoumsaetze_erkannt` |
| `erkannt_kreditor` | ForeignKey | null/blank | — | db_index; → `personen.Person`; on_delete=SET_NULL; related_name=`kontoumsaetze_erkannt` |
| `erkennungs_quelle` | CharField | blank | — | max_length=20; choices: `e2e_id`, `iban_ev`, `bank_match_regel`, `iban_kreditor`, `ki`, `keine` |
| `erkennungs_konfidenz` | DecimalField | null/blank | — | max_digits=3, decimal_places=2 |
| `erkennungs_begruendung` | TextField | blank | — | — |
| `match_regel` | ForeignKey | null/blank | — | db_index; → `buchhaltung.BankMatchRegel`; on_delete=SET_NULL; related_name=`angewendete_umsaetze` |
| `verbucht_am` | DateTimeField | null/blank | — | — |
| `verbucht_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`verbuchte_umsaetze` |
| `notiz` | TextField | blank | — | — |
| `ki_vorschlag` | JSONField | null/blank | — | — |
| `import_datei` | CharField | blank | — | max_length=500 |
| `importiert_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-buchungsdatum', '-importiert_am']`
- `Index(['bankkonto', 'status'], name='idx_ku_bankkonto_status')`
- `Index(['status', 'buchungsdatum'], name='idx_ku_status_datum')`

#### `KreditorOP`

- **Tabelle:** `buchhaltung_kreditorop`
- **Bezeichnung:** Kreditor-OP / Kreditor-OPs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `op_nummer` | IntegerField | — | — | unique |
| `rechnung` | OneToOneField | null/blank | — | unique; → `rechnungen.Rechnung`; on_delete=PROTECT; related_name=`kreditor_op` |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=PROTECT; related_name=`offene_posten` |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`kreditor_ops` |
| `buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`kreditor_op_erstellung` |
| `zahlung_buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`kreditor_op_zahlung` |
| `betrag_ursprung` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `betrag_offen` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `faellig_ab` | DateField | — | — | — |
| `verwendungszweck` | TextField | blank | — | — |
| `herkunft` | CharField | — | `'eingangsrechnung'` | max_length=20; choices: `eingangsrechnung`, `wkz_vorlage`, `manuell` |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `bezahlt`, `teilbezahlt`, `storniert` |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-op_nummer']`

#### `LastschriftLauf`

- **Tabelle:** `buchhaltung_lastschriftlauf`
- **Bezeichnung:** Lastschrift-Lauf / Lastschrift-Läufe

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`lastschrift_laeufe` |
| `hausgeld_sollstellungslauf` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellungslauf`; on_delete=PROTECT; related_name=`lastschrift_laeufe` |
| `bezeichnung` | CharField | blank | — | max_length=255 |
| `faelligkeitsdatum` | DateField | — | — | — |
| `status` | CharField | — | `'erstellt'` | max_length=20; choices: `erstellt`, `exportiert`, `eingereicht` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`lastschrift_laeufe` |
| `anzahl_positionen` | IntegerField | — | `0` | — |
| `gesamt_summe` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `positionen` | JSONField | blank | `list()` | — |
| `ohne_mandat` | JSONField | blank | `list()` | — |
| `buchungen_erstellt` | BooleanField | — | `False` | — |
| `buchungen_datum` | DateField | null/blank | — | — |
| `lauf_quelle` | CharField | — | `'manuell'` | max_length=10; choices: `manuell`, `autopilot` |
| `datei_pfad` | CharField | null/blank | — | max_length=500 |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `Mahnlauf`

- **Tabelle:** `buchhaltung_mahnlauf`
- **Bezeichnung:** Mahnlauf / Mahnläufe

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`mahnlaeufe` |
| `trigger` | CharField | — | `'manuell'` | max_length=12; choices: `automatisch`, `manuell` |
| `status` | CharField | — | `'simulation'` | max_length=20; choices: `simulation`, `ausstehend`, `freigegeben`, `ausgefuehrt`, `fehler` |
| `ausgefuehrt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`mahnlaeufe` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `freigabe_user` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`freigegebene_mahnlaeufe` |
| `freigabe_am` | DateTimeField | null/blank | — | — |
| `anzahl_mahnungen` | IntegerField | — | `0` | — |
| `gesamt_gebuehren` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `gesamt_zinsen` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `protokoll` | JSONField | blank | `list()` | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `Mahnsperre`

- **Tabelle:** `buchhaltung_mahnsperre`
- **Bezeichnung:** Mahnsperre / Mahnsperren

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `personenkonto` | ForeignKey | — | — | db_index; → `konten.Personenkonto`; on_delete=PROTECT; related_name=`mahnsperren` |
| `gesperrt_bis` | DateField | — | — | — |
| `grund` | CharField | — | — | max_length=255 |
| `gesetzt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`gesetzte_mahnsperren` |
| `gesetzt_am` | DateTimeField | blank | — | — |
| `aufgehoben_am` | DateTimeField | null/blank | — | — |
| `aufgehoben_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`aufgehobene_mahnsperren` |

**Meta:**
- `ordering = ['-gesetzt_am']`

#### `Mahnung`

- **Tabelle:** `buchhaltung_mahnung`
- **Bezeichnung:** Mahnung / Mahnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `lauf` | ForeignKey | — | — | db_index; → `buchhaltung.Mahnlauf`; on_delete=CASCADE; related_name=`mahnungen` |
| `personenkonto` | ForeignKey | — | — | db_index; → `konten.Personenkonto`; on_delete=PROTECT; related_name=`mahnungen` |
| `mahnstufe` | IntegerField | — | — | — |
| `offene_posten_summe` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `gebuehr` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `zinsen` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |
| `buchung_gebuehr` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`mahnung_gebuehr` |
| `buchung_zinsen` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`mahnung_zinsen` |
| `pdf_pfad` | CharField | blank | — | max_length=500 |
| `versandt_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-lauf__erstellt_am']`

#### `OffenerPosten`

- **Tabelle:** `buchhaltung_offenerposten`
- **Bezeichnung:** Offener Posten / Offene Posten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `buchung` | OneToOneField | — | — | unique; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`offener_posten` |
| `personenkonto` | ForeignKey | — | — | db_index; → `konten.Personenkonto`; on_delete=PROTECT; related_name=`offene_posten` |
| `betrag_ursprung` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `betrag_offen` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `faellig_ab` | DateField | — | — | — |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `teilverrechnet`, `verrechnet`, `storniert`, `forderungsfall` |
| `mahnstufe` | IntegerField | — | `0` | — |
| `mahnsperre_bis` | DateField | null/blank | — | — |

**Meta:**
- `ordering = ['faellig_ab']`

#### `OposSequenz`

- **Tabelle:** `buchhaltung_opossequenz`
- **Bezeichnung:** OPOS-Sequenz / OPOS-Sequenzen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `objekt` | OneToOneField | — | — | **PK**; → `objekte.Objekt`; on_delete=PROTECT; related_name=`opos_sequenz` |
| `naechste_lfd_nr` | BigIntegerField | — | `1` | — |

#### `RAPAufloesung`

- **Tabelle:** `buchhaltung_rapaufloesung`
- **Bezeichnung:** RAP-Auflösung / RAP-Auflösungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `position` | ForeignKey | — | — | db_index; → `buchhaltung.RAPPosition`; on_delete=CASCADE; related_name=`aufloesungen` |
| `buchungsdatum` | DateField | — | — | — |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`rap_aufloesungen` |
| `status` | CharField | — | `'geplant'` | max_length=10; choices: `geplant`, `gebucht` |

**Meta:**
- `ordering = ['buchungsdatum']`

#### `RAPPosition`

- **Tabelle:** `buchhaltung_rapposition`
- **Bezeichnung:** RAP-Position / RAP-Positionen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`rap_positionen` |
| `bezeichnung` | CharField | — | — | max_length=255 |
| `rap_typ` | CharField | — | — | max_length=4; choices: `ARAP`, `PRAP` |
| `gesamtbetrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `zeitraum_von` | DateField | — | — | — |
| `zeitraum_bis` | DateField | — | — | — |
| `soll_konto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`rap_positionen_soll` |
| `haben_konto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`rap_positionen_haben` |
| `ursprungsbuchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`rap_positionen` |
| `status` | CharField | — | `'aktiv'` | max_length=12; choices: `aktiv`, `aufgeloest` |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`rap_positionen` |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `SepaZahlungslauf`

- **Tabelle:** `buchhaltung_sepazahlungslauf`
- **Bezeichnung:** SEPA-Zahlungslauf / SEPA-Zahlungsläufe

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `faelligkeitsdatum` | DateField | — | — | — |
| `anzahl_rechnungen` | IntegerField | — | `0` | — |
| `summe` | DecimalField | — | `0` | max_digits=14, decimal_places=2 |
| `dateiname` | CharField | blank | `''` | max_length=255 |
| `positionen` | JSONField | blank | `list()` | — |
| `buchungs_fehler` | JSONField | blank | `list()` | — |
| `uebersprungen` | JSONField | blank | `list()` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`sepa_zahlungslaeufe` |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `SollstellungSplit`

- **Tabelle:** `buchhaltung_sollstellungsplit`
- **Bezeichnung:** Sollstellungs-Split / Sollstellungs-Splits

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=CASCADE; related_name=`splits` |
| `ba` | ForeignKey | — | — | db_index; → `buchhaltung.Buchungsart`; on_delete=PROTECT; related_name=`+` |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `bankkonto_ziel` | ForeignKey | null/blank | — | db_index; → `objekte.Bankkonto`; on_delete=PROTECT; related_name=`+` |
| `erloeskonto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`+` |
| `ist_betrag_split` | DecimalField | — | `0` | max_digits=12, decimal_places=2 |

**Meta:**
- `UniqueConstraint(['sollstellung', 'ba'], name='uniq_split_sollstellung_ba')`

#### `SollstellungZahlung`

- **Tabelle:** `buchhaltung_sollstellungzahlung`
- **Bezeichnung:** Sollstellungs-Zahlung / Sollstellungs-Zahlungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`zahlungen` |
| `split` | ForeignKey | null/blank | — | db_index; → `buchhaltung.SollstellungSplit`; on_delete=PROTECT; related_name=`zahlungen` |
| `buchung` | ForeignKey | — | — | db_index; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`sollstellung_zahlungen` |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `tilgungsstufe` | CharField | — | `'hauptforderung'` | max_length=20; choices: `hauptforderung`, `zinsen`, `kosten` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`+` |

**Meta:**
- `ordering = ['erstellt_am']`

#### `WechselKorrekturPaar`

- **Tabelle:** `buchhaltung_wechselkorrekturpaar`
- **Bezeichnung:** Wechsel-Korrektur-Paar / Wechsel-Korrektur-Paare

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wechsel_vorgang` | ForeignKey | — | — | db_index; → `buchhaltung.EigentuemerwechselVorgang`; on_delete=PROTECT; related_name=`korrektur_paare` |
| `periode` | DateField | — | — | — |
| `original_sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wechsel_als_original` |
| `korrektur_sollstellung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wechsel_als_korrektur` |
| `neuanlage_sollstellung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wechsel_als_neuanlage` |
| `original_ist_betrag_vor_korrektur` | DecimalField | — | — | max_digits=14, decimal_places=2 |

**Meta:**
- `ordering = ['periode']`

#### `WiederkehrendeBuchungOP`

- **Tabelle:** `buchhaltung_wiederkehrendebuchungop`
- **Bezeichnung:** WKZ-OP / WKZ-OPs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `vorlage` | ForeignKey | — | — | db_index; → `buchhaltung.WiederkehrendeBuchungVorlage`; on_delete=PROTECT; related_name=`ops` |
| `kreditor_op` | ForeignKey | — | — | db_index; → `buchhaltung.KreditorOP`; on_delete=PROTECT; related_name=`wkz_op` |
| `periode_von` | DateField | — | — | — |
| `periode_bis` | DateField | — | — | — |
| `faellig_am` | DateField | — | — | — |
| `erzeugt_am` | DateTimeField | blank | — | — |
| `bescheid_hochgeladen_am` | DateTimeField | null/blank | — | — |
| `bescheid_hochgeladen_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`wkz_bescheid_uploads` |
| `status` | CharField | — | `'erzeugt'` | max_length=25; choices: `erzeugt`, `bescheid_fehlt`, `ueberweisung_veranlasst`, `bankabgang_erfolgt`, `abweichend_geklaert`, `verworfen` |
| `bank_match_buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`wkz_ops` |
| `abweichung_betrag` | DecimalField | null/blank | — | max_digits=14, decimal_places=2 |
| `klaerungs_grund` | TextField | blank | — | — |

**Meta:**
- `ordering = ['-faellig_am']`
- `UniqueConstraint(['vorlage', 'periode_von', 'periode_bis'], name='wkz_op_unique_periode_je_vorlage')`

#### `WiederkehrendeBuchungSplit`

- **Tabelle:** `buchhaltung_wiederkehrendebuchungsplit`
- **Bezeichnung:** WKZ-Split / WKZ-Splits

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `vorlage` | ForeignKey | — | — | db_index; → `buchhaltung.WiederkehrendeBuchungVorlage`; on_delete=CASCADE; related_name=`splits` |
| `kontonummer` | CharField | — | — | max_length=8 |
| `bezeichnung` | CharField | — | — | max_length=200 |
| `betrag` | DecimalField | — | — | max_digits=14, decimal_places=2 |
| `reihenfolge` | PositiveIntegerField | — | `0` | — |

**Meta:**
- `ordering = ['reihenfolge', 'kontonummer']`
- `CheckConstraint(name='wkz_split_betrag_positiv')`

#### `WiederkehrendeBuchungVorlage`

- **Tabelle:** `buchhaltung_wiederkehrendebuchungvorlage`
- **Bezeichnung:** Wiederkehrende Buchung (Vorlage) / Wiederkehrende Buchungen (Vorlagen)

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`wkz_vorlagen` |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=PROTECT; related_name=`wkz_vorlagen` |
| `bezeichnung` | CharField | — | — | max_length=200 |
| `typ` | CharField | — | — | max_length=10; choices: `bescheid`, `vertrag` |
| `betrag_gesamt` | DecimalField | — | — | max_digits=14, decimal_places=2 |
| `rhythmus` | CharField | — | — | max_length=15; choices: `monatlich`, `zweimonatlich`, `quartalsweise`, `halbjaehrlich`, `jaehrlich`, `frei` |
| `erste_faelligkeit` | DateField | — | — | — |
| `bei_wochenende` | CharField | — | `'zurueck'` | max_length=12; choices: `vor`, `zurueck`, `unveraendert` |
| `vorlauf_tage` | IntegerField | — | `7` | — |
| `toleranz_betrag` | DecimalField | — | `'5.00'` | max_digits=14, decimal_places=2 |
| `toleranz_tage` | IntegerField | — | `14` | — |
| `zahlweg` | CharField | — | `'lastschrift'` | max_length=12; choices: `lastschrift`, `ueberweisung` |
| `sepa_mandat_id` | CharField | blank | — | max_length=35 |
| `bescheid_pflicht` | BooleanField | — | `True` | — |
| `gueltig_ab` | DateField | — | — | — |
| `gueltig_bis` | DateField | null/blank | — | — |
| `status` | CharField | — | `'entwurf'` | max_length=12; choices: `entwurf`, `eingereicht`, `aktiv`, `pausiert`, `beendet` |
| `freigegeben_am` | DateTimeField | null/blank | — | — |
| `freigegeben_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`freigegebene_wkz_vorlagen` |
| `freigabe_jahresbetrag` | DecimalField | null/blank | — | max_digits=14, decimal_places=2 |
| `ersetzt_vorlage` | ForeignKey | null/blank | — | db_index; → `buchhaltung.WiederkehrendeBuchungVorlage`; on_delete=SET_NULL; related_name=`nachfolger_vorlagen` |
| `rechnung` | ForeignKey | null/blank | — | db_index; → `rechnungen.Rechnung`; on_delete=SET_NULL; related_name=`wkz_vorlagen` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_wkz_vorlagen` |
| `geaendert_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['objekt', 'bezeichnung']`
- `CheckConstraint(name='wkz_vorlage_betrag_positiv')`
- `CheckConstraint(name='wkz_vorlage_gueltig_bis_nach_ab')`

#### `WirtschaftsplanBeschluss`

- **Tabelle:** `buchhaltung_wirtschaftsplanbeschluss`
- **Bezeichnung:** Wirtschaftsplan-Beschluss / Wirtschaftsplan-Beschlüsse

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`wirtschaftsplan_beschluesse` |
| `beschluss_typ` | CharField | — | — | max_length=30; choices: `wirtschaftsplan`, `umlaufbeschluss_stundung`, `umlaufbeschluss_sonstig` |
| `beschluss_datum` | DateField | — | — | — |
| `protokoll_position` | CharField | null/blank | — | max_length=50 |
| `wirtschaftsplan_beginn` | DateField | — | — | — |
| `wirtschaftsplan_ende` | DateField | null/blank | — | — |
| `gesamt_volumen` | DecimalField | null/blank | — | max_digits=14, decimal_places=2 |
| `protokoll_dokument` | ForeignKey | null/blank | — | db_index; → `dokumente.Dokument`; on_delete=PROTECT; related_name=`wirtschaftsplan_beschluesse` |
| `notiz` | TextField | null/blank | — | — |
| `status` | CharField | — | `'erfasst'` | max_length=12; choices: `erfasst`, `gebucht`, `storniert` |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_wirtschaftsplan_beschluesse` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `gebucht_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-beschluss_datum']`

#### `WirtschaftsplanKorrekturPaar`

- **Tabelle:** `buchhaltung_wirtschaftsplankorrekturpaar`
- **Bezeichnung:** Wirtschaftsplan-Korrektur-Paar / Wirtschaftsplan-Korrektur-Paare

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `beschluss` | ForeignKey | — | — | db_index; → `buchhaltung.WirtschaftsplanBeschluss`; on_delete=PROTECT; related_name=`korrektur_paare` |
| `eigentumsverhaeltnis` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`wp_korrektur_paare` |
| `periode` | DateField | — | — | — |
| `original_sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wp_als_original` |
| `korrektur_sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wp_als_korrektur` |
| `neuanlage_sollstellung` | ForeignKey | — | — | db_index; → `buchhaltung.HausgeldSollstellung`; on_delete=PROTECT; related_name=`wp_als_neuanlage` |
| `differenz_betrag` | DecimalField | — | — | max_digits=8, decimal_places=2 |

**Meta:**
- `ordering = ['beschluss', 'eigentumsverhaeltnis', 'periode']`

#### `WirtschaftsplanPosition`

- **Tabelle:** `buchhaltung_wirtschaftsplanposition`
- **Bezeichnung:** Wirtschaftsplan-Position / Wirtschaftsplan-Positionen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `beschluss` | ForeignKey | — | — | db_index; → `buchhaltung.WirtschaftsplanBeschluss`; on_delete=PROTECT; related_name=`positionen` |
| `eigentumsverhaeltnis` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=PROTECT; related_name=`wirtschaftsplan_positionen` |
| `buchungsart` | ForeignKey | — | — | db_index; → `buchhaltung.Buchungsart`; on_delete=PROTECT; related_name=`wirtschaftsplan_positionen` |
| `betrag` | DecimalField | — | — | max_digits=8, decimal_places=2 |

**Meta:**
- `ordering = ['beschluss', 'eigentumsverhaeltnis', 'buchungsart']`
- `UniqueConstraint(['beschluss', 'eigentumsverhaeltnis', 'buchungsart'], name='uniq_wp_position_beschluss_ev_ba')`

#### `WirtschaftsplanRuecklage`

- **Tabelle:** `buchhaltung_wirtschaftsplanruecklage`
- **Bezeichnung:** Wirtschaftsplan-Rücklagenzuführung / Wirtschaftsplan-Rücklagenzuführungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wirtschaftsjahr` | ForeignKey | — | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=CASCADE; related_name=`ruecklagen_planwerte` |
| `ba_nr` | CharField | — | — | max_length=3 |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `erfasst_am` | DateTimeField | blank | — | — |
| `erfasst_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`+` |

**Meta:**
- `UniqueConstraint(['wirtschaftsjahr', 'ba_nr'], name='uniq_wp_ruecklage_je_wj_ba')`

### 1.3 App `dokumente`

#### `BelegnummerZaehler`

- **Tabelle:** `dokumente_belegnummerzaehler`
- **Bezeichnung:** Belegnummer-Zähler / Belegnummer-Zählers

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | IntegerField | — | `1` | **PK** |
| `letzter_zaehler` | BigIntegerField | — | `0` | — |

#### `Dokument`

- **Tabelle:** `dokumente_dokument`
- **Bezeichnung:** Dokument / Dokumente

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `datei` | FileField | — | — | max_length=1000 |
| `ablage_wurzel` | CharField | — | `'media'` | max_length=20; choices: `media`, `rechnungen` |
| `dateiname` | CharField | — | — | max_length=255 |
| `kategorie` | CharField | — | — | max_length=100 |
| `beschreibung` | TextField | blank | — | — |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`dokumente` |
| `einheit` | ForeignKey | null/blank | — | db_index; → `objekte.Einheit`; on_delete=PROTECT; related_name=`dokumente` |
| `vorgang` | ForeignKey | null/blank | — | db_index; → `vorgaenge.Vorgang`; on_delete=PROTECT; related_name=`dokumente` |
| `person` | ForeignKey | null/blank | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`dokumente` |
| `version` | IntegerField | — | `1` | — |
| `vorgaenger_version` | ForeignKey | null/blank | — | db_index; → `dokumente.Dokument`; on_delete=PROTECT; related_name=`nachfolger_versionen` |
| `hochgeladen_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`hochgeladene_dokumente` |
| `hochgeladen_am` | DateTimeField | blank | — | — |
| `dokument_typ` | CharField | — | `'sonstiges'` | max_length=20; choices: `beleg`, `vertrag`, `korrespondenz`, `beschluss`, `abrechnung`, `sonstiges` |
| `revisionssicher` | BooleanField | — | `False` | — |
| `revisionssicher_seit` | DateTimeField | null/blank | — | — |
| `sha256` | CharField | null/blank | — | max_length=64; db_index |
| `abgelegt_am` | DateTimeField | blank | — | — |
| `beleg_nummer` | CharField | null/blank | — | max_length=12; unique |

**Meta:**
- `ordering = ['-hochgeladen_am']`
- `CheckConstraint(name='dokument_max_ein_kontext')`

### 1.4 App `handwerker`

#### `AuftragsbestaetigungsToken`

- **Tabelle:** `handwerker_auftragsbestaetigungstoken`
- **Bezeichnung:** Auftragsbestätigungs-Token / Auftragsbestätigungs-Token

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `auftrag` | OneToOneField | — | — | unique; → `handwerker.Handwerkerauftrag`; on_delete=CASCADE; related_name=`token` |
| `accept_token` | CharField | blank | — | max_length=64; unique |
| `reject_token` | CharField | blank | — | max_length=64; unique |
| `gueltig_bis` | DateTimeField | — | — | — |
| `verbraucht_am` | DateTimeField | null/blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |

#### `Gewerk`

- **Tabelle:** `handwerker_gewerk`
- **Bezeichnung:** Gewerk / Gewerke

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `code` | CharField | — | — | max_length=30; unique |
| `bezeichnung` | CharField | — | — | max_length=100 |
| `aktiv` | BooleanField | — | `True` | — |
| `sortierung` | IntegerField | — | `0` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_gewerke` |

**Meta:**
- `ordering = ['sortierung', 'bezeichnung']`

#### `Handwerkerauftrag`

- **Tabelle:** `handwerker_handwerkerauftrag`
- **Bezeichnung:** Handwerkerauftrag / Handwerkeraufträge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `nummer` | CharField | — | — | max_length=20; unique |
| `vorgang` | ForeignKey | null/blank | — | db_index; → `vorgaenge.Vorgang`; on_delete=PROTECT; related_name=`handwerkerauftraege` |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`handwerkerauftraege` |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=PROTECT; related_name=`handwerkerauftraege` |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_handwerkerauftraege` |
| `titel` | CharField | — | — | max_length=255 |
| `beschreibung` | TextField | blank | — | — |
| `gewuenscht_ab` | DateField | null/blank | — | — |
| `prioritaet` | CharField | — | `'normal'` | max_length=10; choices: `niedrig`, `normal`, `hoch` |
| `geschaetzte_kosten` | DecimalField | null/blank | — | max_digits=10, decimal_places=2 |
| `status` | CharField | — | `'entwurf'` | max_length=20; choices: `entwurf`, `versendet`, `angenommen`, `abgelehnt`, `in_arbeit`, `abgeschlossen`, `storniert`, `abgelaufen` |
| `versendet_am` | DateTimeField | null/blank | — | — |
| `angenommen_am` | DateTimeField | null/blank | — | — |
| `abgelehnt_am` | DateTimeField | null/blank | — | — |
| `ablehnung_grund` | TextField | blank | — | — |
| `abgeschlossen_am` | DateTimeField | null/blank | — | — |
| `abschluss_notiz` | TextField | blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `geaendert_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`
- `Index(['objekt', 'status'], name='handwerker__objekt__2aa4bd_idx')`
- `Index(['kreditor', 'status'], name='handwerker__kredito_4f700a_idx')`
- `Index(['erstellt_am'], name='handwerker__erstell_270392_idx')`

#### `HandwerkerauftragEreignis`

- **Tabelle:** `handwerker_handwerkerauftragereignis`
- **Bezeichnung:** Handwerkerauftrag-Ereignis / Handwerkerauftrag-Ereignisse

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `auftrag` | ForeignKey | — | — | db_index; → `handwerker.Handwerkerauftrag`; on_delete=CASCADE; related_name=`ereignisse` |
| `typ` | CharField | — | — | max_length=30; choices: `statuswechsel`, `versand`, `versand_fehlgeschlagen`, `kommentar`, `rechnung_zugeordnet`, `system_abgelaufen` |
| `text` | TextField | null/blank | — | — |
| `alter_wert` | CharField | null/blank | — | max_length=100 |
| `neuer_wert` | CharField | null/blank | — | max_length=100 |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_handwerkerauftrag_ereignisse` |

**Meta:**
- `ordering = ['erstellt_am']`

#### `HandwerkerauftragNummerZaehler`

- **Tabelle:** `handwerker_handwerkerauftragnummerzaehler`
- **Bezeichnung:** Handwerkerauftrag-Nummer-Zähler / Handwerkerauftrag-Nummer-Zähler

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `jahr` | IntegerField | — | — | **PK** |
| `letzter_zaehler` | IntegerField | — | `0` | — |

#### `ObjektHandwerker`

- **Tabelle:** `handwerker_objekthandwerker`
- **Bezeichnung:** Objekt-Handwerker-Zuordnung / Objekt-Handwerker-Zuordnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`handwerker_zuordnungen` |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=CASCADE; related_name=`objekt_zuordnungen` |
| `prioritaet` | PositiveIntegerField | — | `1` | — |
| `notiz` | TextField | blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['prioritaet', 'kreditor__name']`
- `UniqueConstraint(['objekt', 'kreditor'], name='unique_objekt_handwerker')`

### 1.5 App `konten`

#### `Abrechnungsart`

- **Tabelle:** `konten_abrechnungsart`
- **Bezeichnung:** Abrechnungsart / Abrechnungsarten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`abrechnungsarten` |
| `code` | CharField | — | — | max_length=3 |
| `bezeichnung` | CharField | — | — | max_length=100 |
| `aktiv` | BooleanField | — | `True` | — |

**Meta:**
- `ordering = ['code']`
- `unique_together = (('objekt', 'code'),)`

#### `Konto`

- **Tabelle:** `konten_konto`
- **Bezeichnung:** Konto (Sachkonto) / Konten (Sachkonten)

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wirtschaftsjahr` | ForeignKey | null/blank | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=CASCADE; related_name=`konten` |
| `kontonummer` | CharField | — | — | max_length=6 |
| `kontoname` | CharField | — | — | max_length=120 |
| `abrechnungsart` | CharField | null/blank | — | max_length=3 |
| `direktes_buchen` | BooleanField | — | `True` | — |
| `verteilerschluessel` | CharField | null/blank | — | max_length=3 |
| `kontoart` | CharField | — | `Konto.Kontoart.STANDARD` | max_length=12; choices: `standard`, `summierung`, `unterkonto` |
| `arge_konto` | BooleanField | — | `False` | — |
| `arge_kostenart` | CharField | null/blank | — | max_length=20 |
| `aktiv` | BooleanField | — | `True` | — |
| `umlagefaehig` | BooleanField | — | `True` | — |

**Meta:**
- `ordering = ['kontonummer']`
- `UniqueConstraint(['wirtschaftsjahr', 'kontonummer'], name='unique_wj_kontonummer')` condition=(AND: ('wirtschaftsjahr__isnull', False))

#### `KontoVerteilerSchluessel`

- **Tabelle:** `konten_kontoverteilerschluessel`
- **Bezeichnung:** Konto-Verteilerschlüssel / Konto-Verteilerschlüssel

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `konto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=CASCADE; related_name=`vs_zuordnungen` |
| `vs_code` | CharField | — | — | max_length=3 |
| `gueltig_ab` | DateField | — | — | — |

**Meta:**
- `ordering = ['konto', 'gueltig_ab']`

#### `Personenkonto`

- **Tabelle:** `konten_personenkonto`
- **Bezeichnung:** Personenkonto / Personenkonten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`personenkonten` |
| `eigentuemer` | ForeignKey | — | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`personenkonten` |
| `vertrag` | OneToOneField | — | — | unique; → `personen.EigentumsVerhaeltnis`; on_delete=CASCADE; related_name=`personenkonto` |
| `kontonummer` | CharField | — | — | max_length=4 |
| `status` | CharField | — | `'aktiv'` | max_length=20; choices: `aktiv`, `archiviert` |
| `archiviert_am` | DateField | null/blank | — | — |

**Meta:**
- `ordering = ['objekt', 'kontonummer']`
- `unique_together = (('objekt', 'kontonummer'),)`

#### `Unterkonto`

- **Tabelle:** `konten_unterkonto`
- **Bezeichnung:** Unterkonto / Unterkonten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `personenkonto` | ForeignKey | — | — | db_index; → `konten.Personenkonto`; on_delete=CASCADE; related_name=`unterkonten` |
| `suffix` | CharField | — | — | max_length=4 |
| `bezeichnung` | CharField | — | — | max_length=255 |
| `sachkonto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`unterkonten` |
| `bankkonto` | ForeignKey | null/blank | — | db_index; → `objekte.Bankkonto`; on_delete=SET_NULL; related_name=`unterkonten` |

**Meta:**
- `ordering = ['personenkonto', 'suffix']`
- `unique_together = (('personenkonto', 'suffix'),)`

### 1.6 App `massenimport`

#### `ImportJob`

- **Tabelle:** `massenimport_importjob`
- **Bezeichnung:** Import-Job / Import-Jobs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `typ` | CharField | — | `'weg_objekt'` | max_length=20; choices: `weg_objekt`, `personen_import` |
| `datei_pfad` | CharField | blank | — | max_length=500 |
| `status` | CharField | — | `'pending'` | max_length=20; choices: `pending`, `parsed`, `committed`, `failed`, `partial` |
| `preview_token` | UUIDField | null/blank | — | max_length=32; unique |
| `zeilen_gesamt` | PositiveIntegerField | — | `0` | — |
| `zeilen_ok` | PositiveIntegerField | — | `0` | — |
| `zeilen_warnung` | PositiveIntegerField | — | `0` | — |
| `zeilen_fehler` | PositiveIntegerField | — | `0` | — |
| `ergebnis` | JSONField | — | `dict()` | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`import_jobs` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `aktualisiert_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-erstellt_am']`

### 1.7 App `mitarbeiter`

#### `Mitarbeiter`

- **Tabelle:** `mitarbeiter_mitarbeiter`
- **Bezeichnung:** Mitarbeiter / Mitarbeiter

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `user` | OneToOneField | — | — | unique; → `auth.User`; on_delete=CASCADE; related_name=`mitarbeiter_profil` |
| `abteilungen` | ArrayField | — | `list()` | — |
| `telefon` | CharField | blank | — | max_length=30 |
| `aktiv` | BooleanField | — | `True` | — |
| `abwesend` | BooleanField | — | `False` | — |
| `eingetreten_am` | DateField | null/blank | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['user__last_name', 'user__first_name']`

#### `MitarbeiterObjektZuordnung`

- **Tabelle:** `mitarbeiter_mitarbeiterobjektzuordnung`
- **Bezeichnung:** Mitarbeiter-Objekt-Zuordnung / Mitarbeiter-Objekt-Zuordnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `mitarbeiter` | ForeignKey | — | — | db_index; → `mitarbeiter.Mitarbeiter`; on_delete=CASCADE; related_name=`objekt_zuordnungen` |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`mitarbeiter_zuordnungen` |
| `aufgabe` | CharField | blank | `''` | max_length=50; choices: `objektmanagement`, `buchhaltung`, `frontoffice`, `backoffice`, `fm_management`, `geschaeftsfuehrer`, `prokurist`, `auszubildender` |

**Meta:**
- `ordering = ['mitarbeiter__user__last_name']`
- `unique_together = (('mitarbeiter', 'objekt'),)`

### 1.8 App `objekte`

#### `Bankkonto`

- **Tabelle:** `objekte_bankkonto`
- **Bezeichnung:** Bankkonto / Bankkonten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`bankkonten` |
| `konto_typ` | CharField | — | — | max_length=20; choices: `bewirtschaftung`, `ruecklage` |
| `bezeichnung` | CharField | — | — | max_length=255 |
| `iban` | CharField | blank | — | max_length=34 |
| `bic` | CharField | blank | — | max_length=11 |
| `kontoinhaber` | CharField | blank | — | max_length=255 |
| `reihenfolge` | PositiveIntegerField | — | `1` | — |
| `aktiv` | BooleanField | — | `True` | — |
| `zahlungsverkehr` | BooleanField | — | `False` | — |

**Meta:**
- `ordering = ['reihenfolge', 'bezeichnung']`

#### `Eingang`

- **Tabelle:** `objekte_eingang`
- **Bezeichnung:** Eingang / Eingänge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`eingaenge` |
| `bezeichnung` | CharField | — | — | max_length=255 |
| `strasse` | CharField | — | — | max_length=255 |
| `plz` | CharField | — | — | max_length=10 |
| `ort` | CharField | — | — | max_length=100 |

**Meta:**
- `ordering = ['bezeichnung']`

#### `Einheit`

- **Tabelle:** `objekte_einheit`
- **Bezeichnung:** Einheit / Einheiten

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`einheiten` |
| `eingang` | ForeignKey | null/blank | — | db_index; → `objekte.Eingang`; on_delete=SET_NULL; related_name=`einheiten` |
| `flaechennummer` | CharField | blank | — | max_length=20 |
| `einheit_nr` | CharField | — | — | max_length=20 |
| `einheit_typ` | CharField | — | — | max_length=20; choices: `Wohnung`, `Gewerbe`, `Stellplatz`, `Sonstiges` |
| `lage` | CharField | — | — | max_length=255 |
| `umsatzsteuer_abrechnungsart` | CharField | null/blank | — | max_length=10; choices: `brutto`, `netto` |

**Meta:**
- `ordering = ['flaechennummer']`

#### `EinheitVerbrauch`

- **Tabelle:** `objekte_einheitverbrauch`
- **Bezeichnung:** Einheit-Verbrauch / Einheit-Verbräuche

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `wirtschaftsjahr` | ForeignKey | — | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=CASCADE; related_name=`einheit_verbraeuche` |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=CASCADE; related_name=`verbraeuche` |
| `vs_code` | CharField | — | — | max_length=3; choices: `140`, `141`, `142`, `143`, `144`, `145` |
| `wert` | DecimalField | null/blank | — | max_digits=12, decimal_places=4 |
| `einheit_text` | CharField | blank | — | max_length=20 |
| `quelle` | CharField | null/blank | — | max_length=20; choices: `manuell`, `heiwako_import` |

**Meta:**
- `UniqueConstraint(['wirtschaftsjahr', 'einheit', 'vs_code'], name='unique_einheit_verbrauch')`
- `CheckConstraint(name='einheit_verbrauch_valid_vs_code')`

#### `Objekt`

- **Tabelle:** `objekte_objekt`
- **Bezeichnung:** Objekt / Objekte

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objektnummer` | CharField | blank | — | max_length=20; unique |
| `objekt_typ` | CharField | — | — | max_length=10; choices: `WEG`, `ZH`, `SEV` |
| `bezeichnung` | CharField | — | — | max_length=255 |
| `kurzbezeichnung` | CharField | blank | `''` | max_length=50 |
| `strasse` | CharField | — | — | max_length=255 |
| `plz` | CharField | — | — | max_length=10 |
| `ort` | CharField | — | — | max_length=100 |
| `baujahr` | IntegerField | null/blank | — | — |
| `verwaltung_seit` | DateField | — | — | — |
| `wirtschaftsjahr_start` | IntegerField | — | `1` | — |
| `zahlungsfreigabe_grenzen` | JSONField | — | `dict()` | — |
| `status` | CharField | — | `'aktiv'` | max_length=20; choices: `aktiv`, `archiviert` |
| `umsatzsteuer_pflichtig` | BooleanField | — | `False` | — |
| `glaeubiger_id` | CharField | blank | — | max_length=35 |
| `betreuer` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`betreute_objekte` |
| `betreuer_vertretung` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`vertretene_objekte` |
| `auto_pipeline_aktiv` | BooleanField | — | `True` | — |
| `auto_verbuchen_aktiv` | BooleanField | — | `True` | — |
| `bundesland` | CharField | blank | `''` | max_length=50 |
| `handwerker` | ManyToManyField | blank | — | → `rechnungen.Kreditor`; through=`handwerker.ObjektHandwerker`; related_name=`objekte` |

**Meta:**
- `ordering = ['bezeichnung']`

#### `Verteilerschluessel`

- **Tabelle:** `objekte_verteilerschluessel`
- **Bezeichnung:** Verteilerschlüssel / Verteilerschlüssel

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`verteilerschluessel` |
| `schluessel` | CharField | blank | — | max_length=3 |
| `bezeichnung` | CharField | — | — | max_length=80 |
| `vs_typ` | CharField | null/blank | — | max_length=20; choices: `flaeche`, `mea`, `kopf`, `direkt`, `verbrauch` |
| `aktiv` | BooleanField | — | `True` | — |
| `schluessel_typ` | CharField | blank | `''` | max_length=20 |
| `einheit` | CharField | — | `''` | max_length=20 |
| `reihenfolge` | PositiveIntegerField | — | `1` | — |

**Meta:**
- `ordering = ['objekt', 'schluessel', 'bezeichnung']`
- `unique_together = (('objekt', 'bezeichnung'),)`

#### `VerteilerschluesselWert`

- **Tabelle:** `objekte_verteilerschluesselwert`
- **Bezeichnung:** Verteilerschlüssel-Wert / Verteilerschlüssel-Werte

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `schluessel` | ForeignKey | — | — | db_index; → `objekte.Verteilerschluessel`; on_delete=CASCADE; related_name=`werte` |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=CASCADE; related_name=`verteilerschluessel_werte` |
| `wirtschaftsjahr` | IntegerField | — | `0` | — |
| `beteiligt` | BooleanField | — | `True` | — |
| `wert` | DecimalField | null/blank | — | max_digits=12, decimal_places=4 |
| `einzelwert_einheit` | CharField | blank | `''` | max_length=20 |
| `quelle` | CharField | — | `'stammdaten'` | max_length=20; choices: `stammdaten`, `manuell` |

**Meta:**
- `ordering = ['schluessel', 'einheit__einheit_nr']`
- `unique_together = (('schluessel', 'einheit', 'wirtschaftsjahr'),)`

#### `Wirtschaftsjahr`

- **Tabelle:** `objekte_wirtschaftsjahr`
- **Bezeichnung:** Wirtschaftsjahr / Wirtschaftsjahre

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`wirtschaftsjahre` |
| `jahr` | IntegerField | — | — | — |
| `beginn_monat` | IntegerField | — | — | — |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `abgeschlossen` |
| `vorjahr` | ForeignKey | null/blank | — | db_index; → `objekte.Wirtschaftsjahr`; on_delete=SET_NULL; related_name=`folgejahre` |
| `eroeffnet_am` | DateTimeField | blank | — | — |
| `eroeffnet_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`eroeffnete_wirtschaftsjahre` |
| `abgeschlossen_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['objekt', 'jahr']`
- `UniqueConstraint(['objekt', 'jahr'], name='unique_objekt_wirtschaftsjahr')`
- `CheckConstraint(name='wirtschaftsjahr_min_2000')`

### 1.9 App `personen`

#### `EigentumsVerhaeltnis`

- **Tabelle:** `personen_eigentumsverhaeltnis`
- **Bezeichnung:** Eigentumsverhältnis / Eigentumsverhältnisse

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=CASCADE; related_name=`eigentumsverhaeltnisse` |
| `person` | ForeignKey | — | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`eigentumsverhaeltnisse` |
| `beginn` | DateField | — | — | — |
| `ende` | DateField | null/blank | — | — |

**Meta:**
- `ordering = ['-beginn']`
- `UniqueConstraint(['einheit'], name='uniq_aktiver_vertrag_je_einheit')` condition=(AND: ('ende__isnull', True))

#### `HausgeldHistorie`

- **Tabelle:** `personen_hausgeldhistorie`
- **Bezeichnung:** Hausgeld-Historie / Hausgeld-Historien

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `eigentumsverhaeltnis` | ForeignKey | — | — | db_index; → `personen.EigentumsVerhaeltnis`; on_delete=CASCADE; related_name=`hausgeld_eintraege` |
| `abrechnungsart` | ForeignKey | null/blank | — | db_index; → `konten.Abrechnungsart`; on_delete=PROTECT; related_name=`hausgeld_eintraege` |
| `ba` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchungsart`; on_delete=PROTECT; related_name=`hausgeld_historien` |
| `betrag` | DecimalField | — | — | max_digits=10, decimal_places=2 |
| `gueltig_ab` | DateField | — | — | — |
| `gueltig_bis` | DateField | null/blank | — | — |
| `wirtschaftsplan_jahr` | PositiveIntegerField | null/blank | — | — |
| `quelle` | CharField | — | — | max_length=20; choices: `beschluss`, `import` |
| `beschluss` | ForeignKey | null/blank | — | db_index; → `buchhaltung.WirtschaftsplanBeschluss`; on_delete=PROTECT; related_name=`hausgeld_historien` |
| `quelle_wp` | ForeignKey | null/blank | — | db_index; → `abrechnung_wp.Wirtschaftsplan`; on_delete=SET_NULL; related_name=`hausgeld_historien` |
| `import_referenz` | CharField | null/blank | — | max_length=100 |
| `bemerkung` | CharField | blank | — | max_length=200 |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`hausgeld_historien` |
| `erstellt_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab']`
- `UniqueConstraint(['eigentumsverhaeltnis', 'abrechnungsart', 'gueltig_ab'], name='uniq_historie_je_vertrag_abrart_datum')`
- `CheckConstraint(name='hausgeld_historie_quelle_consistency')`
- `Index(['eigentumsverhaeltnis', 'abrechnungsart', '-gueltig_ab'], name='idx_hausgeld_ev_abr_datum')`

#### `Mietvertrag`

- **Tabelle:** `personen_mietvertrag`
- **Bezeichnung:** Mietvertrag / Mietverträge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `einheit` | ForeignKey | — | — | db_index; → `objekte.Einheit`; on_delete=CASCADE; related_name=`mietvertraege` |
| `mieter` | ForeignKey | — | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`mietvertraege` |
| `beginn` | DateField | — | — | — |
| `ende` | DateField | null/blank | — | — |
| `kaltmiete` | DecimalField | — | — | max_digits=10, decimal_places=2 |
| `nebenkosten_vorauszahlung` | DecimalField | — | `0` | max_digits=10, decimal_places=2 |

**Meta:**
- `ordering = ['-beginn']`

#### `Person`

- **Tabelle:** `personen_person`
- **Bezeichnung:** Person / Personen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `personennummer` | CharField | blank | — | max_length=20; unique |
| `person_typ` | CharField | — | — | max_length=100; choices: `100`, `200`, `300`, `400` |
| `anrede` | CharField | blank | `''` | max_length=20; choices: `Herr`, `Frau`, `Eheleute`, `Herren`, `Damen`, `Herr und Frau`, `Firma`, `` |
| `titel` | CharField | blank | `''` | max_length=50 |
| `titel2` | CharField | blank | `''` | max_length=50 |
| `ist_firma` | BooleanField | — | `False` | — |
| `vorname` | CharField | blank | — | max_length=100 |
| `nachname` | CharField | blank | — | max_length=100 |
| `vorname2` | CharField | blank | — | max_length=100 |
| `nachname2` | CharField | blank | — | max_length=100 |
| `firmenname` | CharField | blank | — | max_length=255 |
| `email` | EmailField | blank | — | max_length=254 |
| `telefon` | CharField | blank | — | max_length=50 |
| `emails` | JSONField | — | `list()` | — |
| `telefonnummern` | JSONField | — | `list()` | — |
| `adresse` | TextField | blank | — | — |
| `ibans` | JSONField | — | `list()` | — |
| `briefanrede` | CharField | blank | `''` | max_length=200 |
| `briefanrede2` | CharField | blank | `''` | max_length=200 |
| `sepa_mandat` | ForeignKey | null/blank | — | db_index; → `personen.SEPAMandat`; on_delete=SET_NULL; related_name=`personen` |

**Meta:**
- `ordering = ['nachname', 'vorname', 'firmenname']`

#### `SEPAMandat`

- **Tabelle:** `personen_sepamandat`
- **Bezeichnung:** SEPA-Mandat / SEPA-Mandate

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `mandatsreferenz` | CharField | — | — | max_length=35; unique |
| `iban` | CharField | — | — | max_length=34 |
| `bic` | CharField | blank | — | max_length=11 |
| `unterzeichnet_am` | DateField | — | — | — |
| `aktiv` | BooleanField | — | `True` | — |
| `sequence_type` | CharField | blank | `'RCUR'` | max_length=4; choices: `RCUR`, `FRST` |

**Meta:**
- `ordering = ['-unterzeichnet_am']`

### 1.10 App `prozesse`

#### `Prozess`

- **Tabelle:** `prozesse_prozess`
- **Bezeichnung:** Prozess / Prozesse

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `prozess_typ` | CharField | — | — | max_length=30; choices: `objekt_anlegen`, `eigentuemerwechsel`, `jahresabrechnung`, `mieterwechsel` |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`prozesse` |
| `current_step` | PositiveIntegerField | — | `1` | — |
| `steps_data` | JSONField | — | `dict()` | — |
| `status` | CharField | — | `'aktiv'` | max_length=20; choices: `aktiv`, `abgeschlossen`, `abgebrochen` |
| `gestartet_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`gestartete_prozesse` |
| `gestartet_am` | DateTimeField | blank | — | — |
| `abgeschlossen_am` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-gestartet_am']`

### 1.11 App `rechnungen`

#### `Freigabe`

- **Tabelle:** `rechnungen_freigabe`
- **Bezeichnung:** Freigabe / Freigaben

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `rechnung` | ForeignKey | — | — | db_index; → `rechnungen.Rechnung`; on_delete=CASCADE; related_name=`freigaben` |
| `bearbeiter` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`freigaben` |
| `rolle` | CharField | — | — | max_length=50 |
| `entscheidung` | CharField | — | — | max_length=20; choices: `freigegeben`, `abgelehnt` |
| `begruendung` | TextField | blank | — | — |
| `zeitstempel` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-zeitstempel']`

#### `FreigabelimitDefault`

- **Tabelle:** `rechnungen_freigabelimitdefault`
- **Bezeichnung:** Freigabelimit-Standard / Freigabelimit-Standards

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `grenzen` | JSONField | — | `list()` | — |

#### `Kreditor`

- **Tabelle:** `rechnungen_kreditor`
- **Bezeichnung:** Kreditor / Kreditoren

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `kreditorennummer` | CharField | null/blank | — | max_length=10; unique |
| `name` | CharField | — | — | max_length=255 |
| `name_normalisiert` | CharField | blank | — | max_length=255 |
| `iban` | CharField | null/blank | — | max_length=34; unique |
| `bic` | CharField | blank | — | max_length=11 |
| `strasse` | CharField | blank | — | max_length=255 |
| `plz` | CharField | blank | — | max_length=10 |
| `ort` | CharField | blank | — | max_length=100 |
| `telefon` | CharField | blank | — | max_length=50 |
| `email` | EmailField | blank | — | max_length=254 |
| `aktiv` | BooleanField | — | `True` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `ist_handwerker` | BooleanField | — | `False` | — |
| `kontakt_person` | CharField | blank | — | max_length=200 |
| `gewerke` | ManyToManyField | blank | — | → `handwerker.Gewerk`; related_name=`kreditoren` |

**Meta:**
- `ordering = ['name']`

#### `KreditorRegel`

- **Tabelle:** `rechnungen_kreditorregel`
- **Bezeichnung:** Kreditor-Regel / Kreditor-Regeln

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=CASCADE; related_name=`regeln` |
| `kundennummer` | CharField | blank | — | max_length=50 |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=SET_NULL |
| `konto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=SET_NULL; related_name=`kreditor_regeln` |
| `treffer` | IntegerField | — | `1` | — |
| `zuletzt_angewendet` | DateTimeField | blank | — | — |

**Meta:**
- `unique_together = (('kreditor', 'kundennummer'),)`

#### `Rechnung`

- **Tabelle:** `rechnungen_rechnung`
- **Bezeichnung:** Rechnung / Rechnungen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`rechnungen` |
| `kreditor` | ForeignKey | null/blank | — | db_index; → `rechnungen.Kreditor`; on_delete=SET_NULL; related_name=`rechnungen` |
| `lieferant` | ForeignKey | null/blank | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`rechnungen_als_lieferant` |
| `dateiname` | CharField | blank | — | max_length=500 |
| `pfad` | CharField | blank | — | max_length=1000 |
| `sha256_hash` | CharField | blank | — | max_length=64; db_index |
| `lieferant_name` | CharField | blank | — | max_length=255 |
| `lieferant_normalisiert` | CharField | blank | — | max_length=255 |
| `lieferant_iban` | CharField | blank | — | max_length=34 |
| `rechnungsnummer` | CharField | blank | — | max_length=100 |
| `rechnungsnummer_normalisiert` | CharField | blank | — | max_length=100 |
| `rechnungsdatum` | DateField | null/blank | — | — |
| `faelligkeitsdatum` | DateField | null/blank | — | — |
| `betrag_netto` | DecimalField | null/blank | — | max_digits=12, decimal_places=2 |
| `betrag_brutto` | DecimalField | null/blank | — | max_digits=12, decimal_places=2 |
| `mwst_satz` | DecimalField | null/blank | — | max_digits=5, decimal_places=2 |
| `waehrung` | CharField | — | `'EUR'` | max_length=3 |
| `leistungsbeschreibung` | TextField | blank | — | — |
| `textauszug` | TextField | blank | — | — |
| `status` | CharField | — | `'importiert'` | max_length=20; choices: `importiert`, `duplikat`, `prueffall`, `erfasst`, `erkannt`, `pruefung_match`, `nicht_erkannt`, `in_pruefung`, `in_buchhaltung`, `zur_freigabe`, `freigegeben`, `teilbezahlt`, `bezahlt`, `wkz_beleg`, `abgelehnt`, `storniert`, `fehler` |
| `duplikat_typ` | CharField | blank | — | max_length=30; choices: `hash`, `rechnungsnummer`, `iban_betrag_datum`, `unscharf`, `ocr_unvollstaendig` |
| `duplikat_von` | ForeignKey | null/blank | — | db_index; → `rechnungen.Rechnung`; on_delete=SET_NULL; related_name=`duplikate` |
| `verarbeitungsnotiz` | TextField | blank | — | — |
| `kostenstelle` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`rechnungen` |
| `ki_extraktion` | JSONField | null/blank | — | — |
| `buchung` | ForeignKey | null/blank | — | db_index; → `buchhaltung.Buchung`; on_delete=SET_NULL; related_name=`rechnung` |
| `beleg_dokument` | OneToOneField | null/blank | — | unique; → `dokumente.Dokument`; on_delete=PROTECT; related_name=`rechnung` |
| `handwerkerauftrag` | ForeignKey | null/blank | — | db_index; → `handwerker.Handwerkerauftrag`; on_delete=PROTECT; related_name=`rechnungen` |
| `kundennummer` | CharField | blank | — | max_length=50 |
| `vorgeschlagenes_konto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=SET_NULL; related_name=`vorschlaege` |
| `erfasst_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erfasste_rechnungen` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `leistungstext` | TextField | blank | — | — |
| `leistungstext_hash` | CharField | blank | — | max_length=64; db_index |
| `erkennungs_stufe` | CharField | null/blank | — | max_length=3; choices: `1`, `2`, `3` |
| `routing_ziel` | CharField | blank | — | max_length=20; choices: `limit_workflow`, `objektbetreuer`, `frontoffice` |
| `erkennungs_konfidenz` | JSONField | null/blank | — | — |
| `zugewiesen_an` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`zugewiesene_rechnungen` |
| `match_regel` | ForeignKey | null/blank | — | db_index; → `rechnungen.RechnungsMatchRegel`; on_delete=SET_NULL; related_name=`angewendet_auf` |
| `aufwandskonto` | ForeignKey | null/blank | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`rechnungen_als_aufwand` |
| `op_buchung` | OneToOneField | null/blank | — | unique; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`rechnung_op` |
| `aufwand_buchung` | OneToOneField | null/blank | — | unique; → `buchhaltung.Buchung`; on_delete=PROTECT; related_name=`rechnung_aufwand` |
| `sepa_lastschrift` | BooleanField | — | `False` | — |
| `ist_gutschrift` | BooleanField | — | `False` | — |
| `kostenverursacher` | ForeignKey | null/blank | — | db_index; → `objekte.Einheit`; on_delete=SET_NULL; related_name=`verursachte_rechnungen` |
| `betrag_haushaltsnah` | DecimalField | — | `Decimal('0')` | max_digits=12, decimal_places=2 |
| `ist_schlussrechnung` | BooleanField | — | `False` | — |
| `skonto_prozent` | DecimalField | null/blank | — | max_digits=5, decimal_places=2 |
| `skonto_betrag` | DecimalField | null/blank | — | max_digits=12, decimal_places=2 |
| `skonto_faellig_bis` | DateField | null/blank | — | — |
| `skonto_genutzt` | BooleanField | — | `False` | — |
| `erkennung_gesamt_konfidenz` | DecimalField | null/blank | — | max_digits=5, decimal_places=2 |
| `erkennung_ampel` | CharField | null/blank | — | max_length=5; choices: `gruen`, `gelb`, `rot` |
| `erkennung_details` | JSONField | blank | `dict()` | — |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `RechnungSplitPosition`

- **Tabelle:** `rechnungen_rechnungsplitposition`
- **Bezeichnung:** Rechnung-Split-Position / Rechnung-Split-Positionen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | BigAutoField | blank | — | **PK** |
| `rechnung` | ForeignKey | — | — | db_index; → `rechnungen.Rechnung`; on_delete=CASCADE; related_name=`splits` |
| `aufwandskonto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`+` |
| `betrag` | DecimalField | — | — | max_digits=12, decimal_places=2 |
| `position` | PositiveIntegerField | — | `0` | — |

**Meta:**
- `ordering = ['position', 'id']`

#### `RechnungsBearbeitungsLock`

- **Tabelle:** `rechnungen_rechnungsbearbeitungslock`
- **Bezeichnung:** Bearbeitungs-Lock / Bearbeitungs-Locks

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `rechnung` | OneToOneField | — | — | **PK**; → `rechnungen.Rechnung`; on_delete=CASCADE; related_name=`bearbeitungslock` |
| `user` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=CASCADE; related_name=`rechnungs_locks` |
| `gueltig_bis` | DateTimeField | — | — | — |
| `erstellt_am` | DateTimeField | blank | — | — |

#### `RechnungsErkennungsLog`

- **Tabelle:** `rechnungen_rechnungserkennungslog`
- **Bezeichnung:** Erkennungs-Log / Erkennungs-Logs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `rechnung` | ForeignKey | — | — | db_index; → `rechnungen.Rechnung`; on_delete=CASCADE; related_name=`erkennungs_logs` |
| `zeitpunkt` | DateTimeField | blank | — | — |
| `stufe` | CharField | null/blank | — | max_length=3; choices: `1`, `2`, `3` |
| `routing_ziel` | CharField | blank | — | max_length=20 |
| `auto_gebucht` | BooleanField | — | `False` | — |
| `dimensionen` | JSONField | — | `dict()` | — |
| `regel_treffer` | ForeignKey | null/blank | — | db_index; → `rechnungen.RechnungsMatchRegel`; on_delete=SET_NULL; related_name=`log_eintraege` |
| `ki_aufruf` | BooleanField | — | `False` | — |
| `ki_kosten_token` | PositiveIntegerField | — | `0` | — |
| `ergebnis_status` | CharField | blank | — | max_length=20 |

**Meta:**
- `ordering = ['-zeitpunkt']`

#### `RechnungsMatchRegel`

- **Tabelle:** `rechnungen_rechnungsmatchregel`
- **Bezeichnung:** Rechnungs-Match-Regel / Rechnungs-Match-Regeln

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `kreditor` | ForeignKey | — | — | db_index; → `rechnungen.Kreditor`; on_delete=CASCADE; related_name=`match_regeln` |
| `objekt` | ForeignKey | — | — | db_index; → `objekte.Objekt`; on_delete=CASCADE; related_name=`match_regeln` |
| `leistungstext_hash` | CharField | — | — | max_length=64 |
| `leistungstext_sample` | TextField | blank | — | — |
| `aufwandskonto` | ForeignKey | — | — | db_index; → `konten.Konto`; on_delete=PROTECT; related_name=`match_regeln` |
| `status` | CharField | — | `'aktiv'` | max_length=10; choices: `aktiv`, `veraltet` |
| `trefferzahl` | PositiveIntegerField | — | `1` | — |
| `erstellt_durch` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_match_regeln` |
| `erstellt_aus` | CharField | — | — | max_length=25; choices: `pruefung`, `freigabe_korrektur`, `manuell` |
| `erstellt_am` | DateTimeField | blank | — | — |
| `aktualisiert_am` | DateTimeField | blank | — | — |
| `letzte_anwendung` | DateTimeField | null/blank | — | — |

**Meta:**
- `ordering = ['-trefferzahl', '-letzte_anwendung']`
- `UniqueConstraint(['kreditor', 'objekt', 'leistungstext_hash'], name='unique_aktive_matchregel')` condition=(AND: ('status', 'aktiv'))

#### `Verarbeitungslog`

- **Tabelle:** `rechnungen_verarbeitungslog`
- **Bezeichnung:** Verarbeitungslog / Verarbeitungslogs

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `rechnung` | ForeignKey | null/blank | — | db_index; → `rechnungen.Rechnung`; on_delete=CASCADE; related_name=`logs` |
| `aktion` | CharField | — | — | max_length=100 |
| `status` | CharField | blank | — | max_length=20 |
| `details` | TextField | blank | — | — |
| `zeitpunkt` | DateTimeField | blank | — | — |

**Meta:**
- `ordering = ['-zeitpunkt']`

### 1.12 App `vorgaenge`

#### `Vorgang`

- **Tabelle:** `vorgaenge_vorgang`
- **Bezeichnung:** Vorgang / Vorgänge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `nummer` | CharField | — | — | max_length=20; unique |
| `typ` | ForeignKey | — | — | db_index; → `vorgaenge.VorgangTyp`; on_delete=PROTECT; related_name=`vorgaenge` |
| `quelle` | CharField | — | `'manuell'` | max_length=10; choices: `manuell`, `mail`, `telefon`, `beschluss`, `portal` |
| `objekt` | ForeignKey | null/blank | — | db_index; → `objekte.Objekt`; on_delete=PROTECT; related_name=`vorgaenge` |
| `einheit` | ForeignKey | null/blank | — | db_index; → `objekte.Einheit`; on_delete=PROTECT; related_name=`vorgaenge` |
| `person` | ForeignKey | null/blank | — | db_index; → `personen.Person`; on_delete=PROTECT; related_name=`vorgaenge` |
| `betreff` | CharField | — | — | max_length=200 |
| `beschreibung` | TextField | null/blank | — | — |
| `status` | CharField | — | `'offen'` | max_length=20; choices: `offen`, `in_bearbeitung`, `wartet_extern`, `wiedervorlage`, `erledigt`, `storniert` |
| `prioritaet` | CharField | — | `'normal'` | max_length=10; choices: `niedrig`, `normal`, `hoch` |
| `zugewiesen_an` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=SET_NULL; related_name=`zugewiesene_vorgaenge` |
| `faellig_am` | DateField | null/blank | — | — |
| `wiedervorlage_am` | DateField | null/blank | — | — |
| `mail_referenz` | CharField | null/blank | — | max_length=255 |
| `telefon_rufnummer` | CharField | null/blank | — | max_length=30 |
| `portal_sichtbar` | BooleanField | — | `False` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | — | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_vorgaenge` |
| `geschlossen_am` | DateTimeField | null/blank | — | — |
| `geschlossen_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`geschlossene_vorgaenge` |

**Meta:**
- `ordering = ['-erstellt_am']`

#### `VorgangAntwortVorschlag`

- **Tabelle:** `vorgaenge_vorgangantwortvorschlag`
- **Bezeichnung:** KI-Antwortvorschlag / KI-Antwortvorschläge

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `vorgang` | ForeignKey | — | — | db_index; → `vorgaenge.Vorgang`; on_delete=CASCADE; related_name=`antwort_vorschlaege` |
| `text_ki` | TextField | blank | `''` | — |
| `text` | TextField | blank | `''` | — |
| `status` | CharField | — | `'entwurf'` | max_length=20; choices: `entwurf`, `freigegeben`, `verworfen`, `fehlgeschlagen` |
| `modell` | CharField | blank | `''` | max_length=50 |
| `fehler` | TextField | null/blank | — | — |
| `erzeugt_am` | DateTimeField | blank | — | — |
| `erzeugt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erzeugte_antwort_vorschlaege` |
| `bearbeitet_am` | DateTimeField | null/blank | — | — |
| `bearbeitet_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`bearbeitete_antwort_vorschlaege` |
| `freigegeben_am` | DateTimeField | null/blank | — | — |
| `freigegeben_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`freigegebene_antwort_vorschlaege` |

**Meta:**
- `ordering = ['-erzeugt_am']`
- `UniqueConstraint(['vorgang'], name='uniq_ein_entwurf_je_vorgang')` condition=(AND: ('status', 'entwurf'))

#### `VorgangEreignis`

- **Tabelle:** `vorgaenge_vorgangereignis`
- **Bezeichnung:** Vorgangs-Ereignis / Vorgangs-Ereignisse

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `vorgang` | ForeignKey | — | — | db_index; → `vorgaenge.Vorgang`; on_delete=CASCADE; related_name=`ereignisse` |
| `typ` | CharField | — | — | max_length=30; choices: `kommentar`, `statuswechsel`, `zuweisung_geaendert`, `dokument_verknuepft`, `system_wiedervorlage_faellig`, `antwort_vorschlag_erzeugt`, `antwort_vorschlag_bearbeitet`, `antwort_vorschlag_freigegeben`, `antwort_vorschlag_verworfen`, `handwerker_beauftragt`, `handwerker_angenommen`, `handwerker_abgelehnt`, `handwerker_abgeschlossen`, `handwerker_abgelaufen` |
| `text` | TextField | null/blank | — | — |
| `alter_wert` | CharField | null/blank | — | max_length=100 |
| `neuer_wert` | CharField | null/blank | — | max_length=100 |
| `intern` | BooleanField | — | `True` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_vorgang_ereignisse` |

**Meta:**
- `ordering = ['erstellt_am']`

#### `VorgangNummerZaehler`

- **Tabelle:** `vorgaenge_vorgangnummerzaehler`
- **Bezeichnung:** Vorgang-Nummer-Zähler / Vorgang-Nummer-Zähler

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `jahr` | IntegerField | — | — | **PK** |
| `letzter_zaehler` | IntegerField | — | `0` | — |

#### `VorgangTyp`

- **Tabelle:** `vorgaenge_vorgangtyp`
- **Bezeichnung:** Vorgangs-Typ / Vorgangs-Typen

| Feld | Typ | null/blank | default | Details |
|---|---|---|---|---|
| `id` | UUIDField | — | `uuid4()` | max_length=32; **PK** |
| `code` | CharField | — | — | max_length=30; unique |
| `bezeichnung` | CharField | — | — | max_length=100 |
| `standard_prioritaet` | CharField | — | `'normal'` | max_length=10; choices: `niedrig`, `normal`, `hoch` |
| `aktiv` | BooleanField | — | `True` | — |
| `sortierung` | IntegerField | — | `0` | — |
| `antwort_vorschlag_aktiv` | BooleanField | — | `False` | — |
| `erstellt_am` | DateTimeField | blank | — | — |
| `erstellt_von` | ForeignKey | null/blank | — | db_index; → `auth.User`; on_delete=PROTECT; related_name=`erstellte_vorgang_typen` |

**Meta:**
- `ordering = ['sortierung', 'bezeichnung']`


---

## 2. Migrationsstand

Ausgabe von `python manage.py showmigrations` auf der **produktiven**
Datenbank (Live-Server 87.106.219.148, `docker-compose.prod.yml`).

- **Angewendet: 180**
- **Offen: 0**
- Der lokale Entwicklungsstand ist identisch (180 angewendet, 0 offen, keine
  Abweichung im Vergleich).

Alles, was unten mit `[X]` markiert ist, existiert damit tatsächlich als
Struktur in der produktiven Datenbank.

```text
abrechnung_wp
 [X] 0001_wp_initial
admin
 [X] 0001_initial
 [X] 0002_logentry_remove_auto_add
 [X] 0003_logentry_add_action_flag_choices
auth
 [X] 0001_initial
 [X] 0002_alter_permission_name_max_length
 [X] 0003_alter_user_email_max_length
 [X] 0004_alter_user_username_opts
 [X] 0005_alter_user_last_login_null
 [X] 0006_require_contenttypes_0002
 [X] 0007_alter_validators_add_error_messages
 [X] 0008_alter_user_username_max_length
 [X] 0009_alter_user_last_name_max_length
 [X] 0010_alter_group_name_max_length
 [X] 0011_update_proxy_permissions
 [X] 0012_alter_user_first_name_max_length
buchhaltung
 [X] 0001_initial
 [X] 0002_buchungsmodul
 [X] 0003_buchung_personenkonto
 [X] 0004_buchung_sammelbuchung
 [X] 0005_buchung_soll_unterkonto
 [X] 0006_buchungsstapel
 [X] 0007_sollstellung_buchungsart_nullable
 [X] 0008_import_ordner_einstellung
 [X] 0009_importordner_global
 [X] 0010_camt_global_kontoumsatz_objekt_nullable
 [X] 0011_camtimportlog
 [X] 0012_lastschriftlauf
 [X] 0013_lastschriftlauf_buchungen_erstellt
 [X] 0014_kreditor_op
 [X] 0015_buchung_erstellt_von_nullable
 [X] 0016_buchung_wirtschaftsjahr_fk
 [X] 0017_hausgeld_nebenbuch
 [X] 0018_hausgeld_lauf_freigabe
 [X] 0019_lastschriftlauf_hg_fk
 [X] 0020_drop_alte_sollstellung_welt
 [X] 0021_seed_buchungsarten
 [X] 0022_buchungsart_buchungstyp
 [X] 0023_camtimporteinstellung_objekt
 [X] 0024_sollstellung_bankkonto_nullable_und_lauf_fehler
 [X] 0025_autopilot_user
 [X] 0026_auto_pipeline_models
 [X] 0027_frontoffice_aufgabe
 [X] 0028_hausgeld_korrektur_felder
 [X] 0029_korrektur_service_v1_2
 [X] 0030_eigentuemerwechsel_vorgang
 [X] 0031_wirtschaftsplan_a1
 [X] 0032_ebanking_phase_a
 [X] 0033_ebanking_backfill
 [X] 0015_wkz_models
 [X] 0016_wj_buchungsart_felder_kreditor
 [X] 0017_buchung_wirtschaftsjahr_nr
 [X] 0034_merge_20260525_0049
 [X] 0035_alter_buchung_wirtschaftsjahr_and_more
 [X] 0036_alter_buchung_wirtschaftsjahr
 [X] 0037_hgsollstellungslauf_add_wirtschaftsjahr
 [X] 0038_sollstellung_wp_felder
 [X] 0039_sepa_zahlungslauf_protokoll
 [X] 0040_wkz_vorlage_status_eingereicht
 [X] 0041_sollstellungslauf_unique_constraint_fix
 [X] 0042_wkz_vorlage_rechnung_fk
 [X] 0043_buchungsart_richtung
 [X] 0044_hga_jahresabrechnung_umbau
 [X] 0045_hga_negative_abrechnungsergebnis
 [X] 0046_einzelabrechnung_ruecklagen_zufuehrung_gesamt_and_more
 [X] 0047_wirtschaftsplanruecklage
 [X] 0048_sollstellung_typ_saldovortrag
 [X] 0049_saldovortrag_negativ
 [X] 0050_buchungsart_saldovortrag
 [X] 0051_wkz_zahlweg
contenttypes
 [X] 0001_initial
 [X] 0002_remove_content_type_name
dokumente
 [X] 0001_initial
 [X] 0002_add_beleg_belegnummerzaehler
 [X] 0003_dokument_abgelegt_am_dokument_beleg_nummer_and_more
 [X] 0004_dokument_ablage_wurzel_alter_dokument_datei
 [X] 0005_delete_beleg
 [X] 0006_dokument_person_dokument_version_and_more
 [X] 0007_beleg_dokumente_kontext_bereinigen
 [X] 0008_dokument_dokument_max_ein_kontext
 [X] 0009_entferne_verknuepfung_typ
handwerker
 [X] 0001_initial
 [X] 0002_seed_gewerk
konten
 [X] 0001_initial
 [X] 0002_konto_update
 [X] 0003_abrechnungsart
 [X] 0004_konto_wirtschaftsjahr_kvs
 [X] 0005_data_migration_wj
 [X] 0004_konto_objekt_nullable
 [X] 0006_merge_20260525_0049
 [X] 0007_remove_konto_objekt
 [X] 0008_konto_umlagefaehig
massenimport
 [X] 0001_initial
 [X] 0002_importjob_personen_import
mitarbeiter
 [X] 0001_initial
 [X] 0002_mitarbeiter_objekt_zuordnung
 [X] 0003_mitarbeiterobjektzuordnung_aufgabe
 [X] 0004_add_abwesend
 [X] 0005_mitarbeiter_freigabe_limit
 [X] 0006_remove_mitarbeiter_freigabe_limit
objekte
 [X] 0001_initial
 [X] 0002_verteilerschluessel_verteilerschluesselwert
 [X] 0003_liegenschaft_anschrift_typ_objekt_objektnummer
 [X] 0004_remove_liegenschaft_anschrift_typ_and_more
 [X] 0005_remove_einheit_liegenschaft_eingang_einheit_eingang_and_more
 [X] 0006_remove_einheit_flaeche_qm_and_more
 [X] 0007_einheit_flaechennummer
 [X] 0008_alter_bankkonto_iban
 [X] 0009_vs_update
 [X] 0010_alter_einheit_options_alter_eingang_bezeichnung_and_more
 [X] 0011_remove_vs101
 [X] 0012_objekt_glaeubiger_id
 [X] 0013_add_betreuer
 [X] 0014_datenmigration_betreuer
 [X] 0015_wirtschaftsjahr_einheitverbrauch
 [X] 0016_bankkonto_zahlungsverkehr
 [X] 0017_objekt_kurzbezeichnung
 [X] 0018_objekt_auto_pipeline
 [X] 0019_ebanking_phase_a
 [X] 0015_objekt_kurzbezeichnung
 [X] 0016_objekt_pipeline_felder
 [X] 0017_bankkonto_zahlungsverkehr
 [X] 0020_merge_20260525_0049
 [X] 0021_alter_objekt_auto_pipeline_aktiv_and_more
 [X] 0022_objekt_handwerker
personen
 [X] 0001_initial
 [X] 0002_person_personennummer
 [X] 0003_person_typ_nummern
 [X] 0004_hausgeldhistorie_kontoart
 [X] 0005_person_anrede
 [X] 0006_person_vorname2_nachname2
 [X] 0007_briefanrede
 [X] 0008_briefanrede2
 [X] 0009_hausgeldhistorie_abrechnungsart
 [X] 0010_hausgeldhistorie_ba
 [X] 0011_sepamandat_sequence_type
 [X] 0012_korrektur_service_v1_2
 [X] 0013_wirtschaftsplan_a1
 [X] 0007_wj_branch_felder
 [X] 0008_hausgeldhistorie_kontoart
 [X] 0009_alter_hausgeldhistorie_quelle_and_more
 [X] 0014_merge_20260525_0049
 [X] 0015_remove_hausgeldhistorie_kontoart_and_more
 [X] 0016_hausgeldhistorie_quelle_wp
 [X] 0017_person_titel
 [X] 0018_person_titel2
 [X] 0019_person_emails_telefonnummern
prozesse
 [X] 0001_initial
rechnungen
 [X] 0001_initial
 [X] 0002_kreditor_alter_rechnung_options_rechnung_dateiname_and_more
 [X] 0003_rechnung_kundennummer_rechnung_vorgeschlagenes_konto_and_more
 [X] 0004_freigabelimitdefault
 [X] 0005_erkennung_stufen
 [X] 0006_kreditor_add_bic
 [X] 0007_v12_routing
 [X] 0008_op_buchung
 [X] 0009_kreditor_nummer
 [X] 0010_v13_aufwandskonto
 [X] 0011_alter_rechnung_erkennungs_stufe_and_more
 [X] 0012_rechnung_sepa_lastschrift
 [X] 0011_wkz_models
 [X] 0013_merge_0011_wkz_models_0012_rechnung_sepa_lastschrift
 [X] 0014_rechnung_ist_gutschrift
 [X] 0015_rechnung_split_position
 [X] 0016_rechnung_betrag_haushaltsnah_and_more
 [X] 0017_alter_rechnung_status
 [X] 0018_in_freigabe_zu_zur_freigabe
 [X] 0019_alter_rechnung_status
 [X] 0020_gebucht_zu_freigegeben
 [X] 0021_rechnung_beleg_dokument
 [X] 0022_remove_rechnung_pdf_upload
 [X] 0023_rechnung_status_wkz_beleg
 [X] 0024_kreditor_gewerk_kreditor_ist_handwerker_and_more
 [X] 0025_kreditor_gewerke_m2m
sessions
 [X] 0001_initial
vorgaenge
 [X] 0001_initial
 [X] 0002_seed_vorgangtyp
 [X] 0003_vorgangtyp_antwort_vorschlag_aktiv_and_more
 [X] 0004_seed_antwort_vorschlag_aktiv
 [X] 0005_vorgangereignis_intern_alter_vorgangereignis_typ
```

### 2.1 Abweichung Datenbank ↔ Code

| Sachverhalt | Status |
|---|---|
| Tabelle `tickets_ticket` | Existiert produktiv noch (0 Zeilen). Lokal per `migrate tickets zero` abgebaut; auf Live nie, weil die App aus `INSTALLED_APPS` entfernt wurde und `migrate` sie damit nicht mehr anfasst. Funktional wirkungslos, kein Code referenziert sie |
| Spalte `dokumente_dokument.verknuepfung_typ` | Produktiv entfernt (Migration `dokumente.0009`) |
| Constraint `dokument_max_ein_kontext` | Produktiv aktiv |

---

## 3. Modul-Status-Matrix

Legende: ✅ vollständig · ⚠️ teilweise · 🔧 fertig, aber Konfiguration fehlt · ❌ nicht vorhanden

| Modul | Spec-Version | Code-Status | Bekannte Deltas |
|---|---|---|---|
| Hausgeld-Nebenbuch | v1.1 (`docs/CLAUDE_CODE_ANLEITUNG_HAUSGELD_NEBENBUCH_v1_1.md`) | ✅ Fertig | Keine |
| OP-Buchung (§ 28 WEG, 3-Phasen) | v1.1 (`..._OP_BUCHUNG_v1_1.md`) | ✅ Fertig | Drei Nummernkreise laufen parallel (`belegnr`, `op_nummer`, `beleg_nummer`) |
| Buchungsnummer / Kreditoren-OP | v1.0 | ✅ Fertig | Keine |
| Rechnungserkennung 3-stufig | v1.3 (`..._Rechnungserkennung_3stufig_v1_3.md`) | ✅ Fertig | OCR benötigt `ANTHROPIC_API_KEY`; Prod-Image ohne `fitz`/`pytesseract` (Direktübergabe an Claude) |
| Rechnungseingang-Umbau | v1.1 | ✅ Fertig | Keine |
| Beleg-Dokument-Kopplung (DMS-Basis) | v1.1 | ✅ Fertig, live | `Rechnung.pfad` läuft weiterhin im Doppelbetrieb; Ablösung für v1_2 vorgesehen |
| Vorgang & DMS (Ticket-Ablösung) | v1.0 | ✅ Fertig, live | Leere Tabelle `tickets_ticket` existiert produktiv noch (lokal gedroppt, live nicht — harmlos, 0 Zeilen) |
| KI-Antwortvorschlag | ohne Spec (Folgeauftrag) | ✅ Fertig, live | Benötigt `ANTHROPIC_API_KEY`; Modell aus `ANTHROPIC_MODEL` |
| Interne Kommentare / Portal-Trennung | ohne Spec (Folgeauftrag) | ✅ Fertig, live | Nur Datengrundlage + Vorschau. Dateifreigabe für Eigentümer bewusst nicht enthalten |
| Handwerkerauftrag | v1.0 (`..._HANDWERKERAUFTRAG_v1_0.md`) | 🔧 Fertig, live — inaktiv | `.env.prod` ohne `EMAIL_BACKEND`/`EMAIL_HOST`/`FRONTEND_BASE_URL` → Versand wird bewusst verweigert. Kein Kreditor hat `ist_handwerker=True`. Spec-Phase E (Rechnungsverkettung per Mail-Intake) durch manuelle Zuordnung ersetzt |
| Jahresabrechnung | v1.0 (`..._JAHRESABRECHNUNG_v1_0.md`) | ✅ Fertig | 7 Services vorhanden (Einzelabrechnung, Verteilerschlüssel, Rücklagen, Kostenstellen, Freigabe, PDF, Wizard) |
| Wirtschaftsplan-Beschluss | v1.2 | ✅ Fertig (Phasen A+B) | Frontend-Ausbau nicht Teil der Spec-Phasen A/B |
| Wirtschaftsplan (abrechnung_wp) | ohne eigene Spec | ✅ Fertig | Keine |
| Wirtschaftsjahre | v1.0 | ✅ Fertig | `Konto.objekt` ist Property, kein DB-Feld — Konto hängt am Wirtschaftsjahr |
| Eigentümerwechsel | v1.0 | ✅ Fertig (Phasen A–C) | Phase D (Cleanup alter Wizard) offen |
| Rückwirkender Eigentümerwechsel | v1.1 | ✅ Fertig (Phase A) | Auszahlungs-Service A3 bewusst übersprungen |
| KorrekturService | v1.2 | ✅ Fertig (Phase A) | Keine |
| WKZ / Wiederkehrende Buchungen | v1.0 | ✅ Fertig | Phase D (Cleanup) offen |
| Auto-Pipeline Hausgeld | v1.1 | ✅ Fertig (Phasen A–E) | Läuft täglich 02:00 per Beat |
| SEPA-Lastschrift & -Export | ohne eigene Spec | ✅ Fertig | pain.008 und pain.001 vorhanden |
| Mahnwesen | `docs/mahnwesen_pflicht_filter.md` | ✅ Fertig | Keine |
| Zinsen | ohne Spec | ✅ Fertig | Keine |
| Saldovortrag | ohne Spec | ⚠️ Teilweise | Laut Projektnotiz sandbox-only, nicht live gerollt — **nicht verifiziert** |
| E-Banking / camt.053 | v1.0 (`..._EBanking_v1_0.md`) | ⚠️ Teilweise | Import produktiv über Beat-Task `camt_ordner_scan` (alle 2 h). `zahlungs_zuordnung_service` existiert; Tilgungslogik bei Zahlungseingang laut Projektnotizen unvollständig. camt.054 als eigener Service vorhanden |
| Cleanup alte Sollstellung | v1.0 | ✅ Abgeschlossen | Alte Modelle entfernt |
| Vertragsmanagement-Import | v1.0 | ✅ Fertig | Keine |
| Personen-Import Ergebnisdatei | v1.0 | ✅ Fertig | Keine |
| Massenimport | ohne Spec | ✅ Fertig | Keine Services, rein View-/Command-basiert |
| Prozesse (Wizards) | ohne Spec | ✅ Fertig | Objektanlage und Eigentümerwechsel |
| KI-Abfrage (Katalog) | ohne Spec | ✅ Fertig | Katalogeintrag `tickets_offen` mit der Ticket-Ablösung entfernt |
| **Mail-Intake-Pipeline** | v1.0 laut Aufgabenstellung | ❌ **Nicht vorhanden** | Es existiert **kein** Mail-Intake (kein Microsoft Graph, kein IMAP). Rechnungen kommen ausschließlich über Ordner-Scan (`rechnungen.ordner_scan`, alle 5 min) plus OCR. Die Vorgang-Spec hatte das Modul ausdrücklich ausgeklammert |
| **Eigentümer-Portal** | keine Spec | ❌ **Nicht vorhanden** | Keine Portal-Endpunkte, kein Auth-Layer für Externe. Vorbereitet sind `Vorgang.portal_sichtbar`, `quelle='portal'` und der Lesepfad `portal-vorschau`. Blockiert bis Multi-Tenancy und Pentest |
| Telefonie-Anbindung | keine Spec | ❌ Nicht vorhanden | Vorbereitet: `Vorgang.quelle='telefon'`, `telefon_rufnummer` |
| Beschlusssammlung (§ 24 Abs. 7 WEG) | keine Spec | ❌ Nicht vorhanden | Vorbereitet: `Vorgang.quelle='beschluss'`, bewusst ohne FK |
| Benachrichtigungssystem | keine Spec | ❌ Nicht vorhanden | `vorgaenge.pruefe_wiedervorlagen` loggt nur, statt zu benachrichtigen — im Code als solches vermerkt |

### 3.1 Korrekturen zur Aufgabenstellung

- **Mail-Intake-Pipeline** war in der Vorlage als „✅ Fertig" geführt. Das ist
  nicht der Fall: Es gibt keine Mail-Eingangsverarbeitung. Rechnungen gelangen
  über einen SFTP-/Ordner-Scan ins System.
- **Rechnungserkennung** liegt als Spec in **v1.3** vor, nicht v1.2.

---

## 4. Management-Commands

| Command | App | Zweck (aus Docstring/`help`) | Parameter |
|---|---|---|---|
| `autopipeline_lauf` | `apps.buchhaltung` | Autopipeline (Sollstellungen + Lastschriften) manuell für einen Monat ausführen | `--monat`, `--objekt`, `--dry-run`, `--stichtag`, `--force` |
| `camt_watch` | `apps.buchhaltung` | Überwacht CamtDAT-Ordner und importiert neue camt.053 XML-Dateien | `--ordner`, `--intervall`, `--objekt` |
| `check_op_konsistenz` | `apps.rechnungen` | Prüft OP-Konsistenz: freigegeben haben aufwandskonto, bezahlt haben aufwand_buchung. | keine |
| `erkennung_bestand` | `apps.rechnungen` | Erkennungs-Pipeline auf Bestandsrechnungen ausführen | `--dry-run`, `--status`, `--verbose`, `--batch-size`, `--monat` |
| `export_testdaten` | `apps.objekte` | Exportiert Einheiten, Personen und Verträge eines Objekts als Import-CSV | `--objekt`, `--output` |
| `import_buchungsarten_csv` | `apps.buchhaltung` | Importiert Buchungsarten aus buchungsarten.csv (Semikolon-getrennt) | `--csv`, `--dry-run` |
| `konten_konsolidieren` | `apps.konten` | Konsolidiert doppelte Sachkonten eines Objekts (gleiche Kontonummer, mehrere WJ) | `--objekt`, `--dry-run` |
| `load_musterkontenrahmen` | `apps.konten` | Legt Musterkontenrahmen WEG (70 Konten) für ein Objekt an. | `--objekt` |
| `migriere_rechnungsbelege` | `apps.dokumente` | Migriert Rechnung.pfad-Altbelege in Dokument (Phase C, Beleg↔Dokument-Kopplung). | `--dry-run`, `--limit`, `--sperren`, `--rueckabwicklung`, `--erlaube-fehlende`, `--user`, `--erlaube-vorhandenen-zaehlerstand` |
| `rechnung_watch` | `apps.rechnungen` | Überwacht Rechnungseingangsordner und importiert neue Dateien mit OCR + KI | `--ordner`, `--intervall` |
| `reset_data` | `apps.objekte` | Löscht alle Geschäftsdaten für Neu-Import. Importordner-Einstellungen (CAMT + Rechnungen) bleiben erhalten. | `--force`, `--dry-run` |
| `seed_buchungsarten` | `apps.buchhaltung` | Legt die Standard-Buchungsarten (BA-Katalog) an (idempotent) | keine |
| `setup_stammdaten` | `apps.objekte` | Legt Kontenrahmen, Abrechnungsarten und Verteilerschluessel fuer Objekte an (Nachholimport) | `--objektnummer`, `--dry-run` |
| `setup_testjahr` | `apps.buchhaltung` | Legt für ein Objekt ein Testjahr mit Sollstellungen und Zahlungen an. | `--objekt`, `--jahr`, `--referenzjahr`, `--dry-run`, `--keine-zahlungen`, `--vertraege-nicht-aktivieren` |
| `setup_testkosten` | `apps.buchhaltung` | Bucht Testkosten (Aufwand an Bank) auf Sachkonten eines Bereichs. | `--objekt`, `--jahr`, `--anzahl`, `--von`, `--bis`, `--min`, `--max`, `--dry-run`, `--force` |

## 5. Celery / Hintergrundjobs

Quelle: `@shared_task`-Deklarationen im Quellcode und `CELERY_BEAT_SCHEDULE` in
`backend/config/settings.py`. (Eine Laufzeit-Abfrage der Task-Registry liefert
in einer `manage.py shell`-Session eine leere Liste, weil Celery seine Tasks
erst bei Bedarf lädt — daher die Erhebung aus dem Quellcode.)

### 5.1 Alle registrierten Tasks

| Task-Name | Datei | Zweck | Auslöser |
|---|---|---|---|
| `buchhaltung.auto_hausgeld_pipeline` | `apps/buchhaltung/tasks.py:16` | Automatischer Hausgeld-Sollstellungslauf inkl. SEPA-Lastschrift je Objekt (`auto_pipeline_aktiv`) | Beat, täglich 02:00 |
| `buchhaltung.archiviere_alte_pain_dateien` | `apps/buchhaltung/tasks.py:62` | Räumt alte pain.008-Dateien aus dem Ausgabeverzeichnis | Beat, montags 03:00 |
| `buchhaltung.erzeuge_faellige_wkz_ops` | `apps/buchhaltung/tasks.py:248` | Erzeugt fällige offene Posten aus wiederkehrenden Buchungsvorlagen | Beat, täglich 03:00 |
| `buchhaltung.camt_ordner_scan` | `apps/buchhaltung/tasks.py:266` | Liest CAMT-053-Dateien aus dem Eingangsordner und importiert Kontoumsätze je IBAN | Beat, alle 2 h (7200 s) |
| `rechnungen.ordner_scan` | `apps/rechnungen/tasks.py:69` | Scannt den Rechnungseingangsordner, startet OCR und Erkennung | Beat, alle 5 min (300 s) |
| `dokumente.ordner_scan` | `apps/dokumente/tasks.py:51` | **Stillgelegt** — Dokumentenanlage wurde im Rahmen der DMS-Umstellung deaktiviert, der Task loggt nur noch. Ersatz als „DMS-Eingangskorb" ist separat zu spezifizieren | Beat, alle 5 min (300 s) |
| `vorgaenge.pruefe_wiedervorlagen` | `apps/vorgaenge/tasks.py:19` | Führt Vorgänge mit erreichtem Wiedervorlagedatum auf `in_bearbeitung` zurück und schreibt ein Systemereignis | Beat, täglich 06:00 |
| `vorgaenge.erzeuge_antwort_vorschlag` | `apps/vorgaenge/tasks.py:77` | Erzeugt den KI-Antwortvorschlag zu einem neuen Vorgang | ereignisgesteuert (`transaction.on_commit` bei der Vorgangsanlage) |
| `handwerker.versende_auftragsmail` | `apps/handwerker/tasks.py:60` | Rendert und versendet die Auftragsmail mit den Token-Links; verbucht Erfolg bzw. Versandfehler | ereignisgesteuert (Anlage und erneuter Versand) |
| `handwerker.benachrichtige_intern` | `apps/handwerker/tasks.py:238` | Informiert intern über Zusage oder Ablehnung durch den Handwerker | ereignisgesteuert (Token-Einlösung) |
| `handwerker.pruefe_abgelaufene_auftraege` | `apps/handwerker/tasks.py:316` | Setzt versendete Aufträge mit abgelaufenem Token auf `abgelaufen` | Beat, täglich 07:00 |

**Summe: 11 Tasks**, davon 8 im Beat-Schedule und 3 ereignisgesteuert.

### 5.2 Beat-Schedule (`CELERY_BEAT_SCHEDULE`)

```python
CELERY_BEAT_SCHEDULE = {
    'camt-ordner-scan-alle-2h': {
        'task': 'buchhaltung.camt_ordner_scan',
        'schedule': 7200,
    },
    'rechnungen-ordner-scan-alle-5min': {
        'task': 'rechnungen.ordner_scan',
        'schedule': 300,
    },
    'dokumente-ordner-scan-alle-5min': {
        'task': 'dokumente.ordner_scan',
        'schedule': 300,
    },
    'wkz-ops-taeglich-03uhr': {
        'task': 'buchhaltung.erzeuge_faellige_wkz_ops',
        'schedule': celery_crontab(hour=3, minute=0) if celery_crontab else 86400,
    },
    'auto-hausgeld-pipeline': {
        'task': 'buchhaltung.auto_hausgeld_pipeline',
        'schedule': crontab(hour=2, minute=0),
    },
    'archiviere-alte-pain-dateien': {
        'task': 'buchhaltung.archiviere_alte_pain_dateien',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),
    },
    'vorgaenge-pruefe-wiedervorlagen-taeglich-06uhr': {
        'task': 'vorgaenge.pruefe_wiedervorlagen',
        'schedule': crontab(hour=6, minute=0),
    },
    'handwerker-pruefe-abgelaufene-auftraege-taeglich-07uhr': {
        'task': 'handwerker.pruefe_abgelaufene_auftraege',
        'schedule': crontab(hour=7, minute=0),
    },
}
```

### 5.3 Zeitplan chronologisch

| Uhrzeit / Intervall | Task |
|---|---|
| alle 5 Minuten | `rechnungen.ordner_scan`, `dokumente.ordner_scan` (stillgelegt) |
| alle 2 Stunden | `buchhaltung.camt_ordner_scan` |
| täglich 02:00 | `buchhaltung.auto_hausgeld_pipeline` |
| täglich 03:00 | `buchhaltung.erzeuge_faellige_wkz_ops` |
| täglich 06:00 | `vorgaenge.pruefe_wiedervorlagen` |
| täglich 07:00 | `handwerker.pruefe_abgelaufene_auftraege` |
| montags 03:00 | `buchhaltung.archiviere_alte_pain_dateien` |

Zeitzone: `CELERY_TIMEZONE = TIME_ZONE = 'Europe/Berlin'`.

### 5.4 Betriebshinweis

Der Celery-Worker lädt die Modelldefinitionen beim Start. Nach Modell- oder
Migrationsänderungen muss er neu gestartet werden
(`docker restart immocore_celery_worker`), sonst arbeitet er mit veraltetem
Schema-Wissen weiter und Tasks scheitern still. Task-Ausgaben — einschließlich
der Mails im Konsolen-Backend — stehen im **Worker**-Log, nicht im Backend-Log.

---

## 6. Inhalt der Stammdaten-Excel-Dateien

Alle drei Dateien liegen im Projektwurzelverzeichnis und sind versioniert. Blätter ohne eigene Kopfzeile erhalten generische Spaltenbezeichnungen, damit keine Datenzeile als Kopf verloren geht.

### 6.1 `Musterkontenrahmen WEG.xlsx`

**Blatt `Sachkonten`** (70 Datenzeilen, 8 Spalten)

| Kontonummer | Kontoname | Abrechnungsart | Direktes Buchen | VS=Verteilerschlüssel | Kontoart | ARGE-Konto | ARGE-Kostenart |
|---|---|---|---|---|---|---|---|
| 09911 | Rücklagenbestandskonto |  | nein |  | Standardkonto | 0 |  |
| 13600 | DCL-Kreditor |  | nein |  | Standardkonto | 0 |  |
| 13650 | DCL-Debitor |  | nein |  | Standardkonto | 0 |  |
| 13700 | Ungeklärte Posten |  | ja |  | Standardkonto | 0 |  |
| 14600 | Bankübertrag / Geldtransit |  | ja |  | Standardkonto | 0 |  |
| 16000 | Kasse |  | ja |  | Standardkonto | 0 |  |
| 18000 | Bank 1 |  | nein |  | Standardkonto | 0 |  |
| 18911 | Bank 2 Rücklage 1 |  | nein |  | Standardkonto | 0 |  |
| 19000 | Aktive Rechnungsabgrenzung (Folgejahr) |  | ja |  | Standardkonto | 0 |  |
| 39000 | Passive Rechnungsabgrenzung (Vorjahr) |  | ja |  | Standardkonto | 0 |  |
| 41900 | Erlöse Hausgeld VZ | 900 | nein |  | Standardkonto | 0 |  |
| 41911 | Erlöse Rücklage I | 911 | nein |  | Standardkonto | 0 |  |
| 41930 | Erlöse Sonderumlage | 930 | nein |  | Standardkonto | 0 |  |
| 41940 | Erlöse Mahngebühren | 940 | nein |  | Standardkonto | 0 |  |
| 41941 | Erlöse Rücklastschriftgebühren | 941 | nein |  | Standardkonto | 0 |  |
| 41950 | Erlöse Abrechnung VJ | 950 | nein |  | Standardkonto | 0 |  |
| 49500 | Erlöse aus Hausgeldklagen | 900 | nein |  | Standardkonto | 0 |  |
| 49600 | sonstige Erlöse | 900 | nein |  | Standardkonto | 0 |  |
| 49700 | Erlöse Versicherungsentschädigungen | 900 | nein |  | Standardkonto | 0 |  |
| 49911 | Erlöse Entnahme IHR I | 900 | nein |  | Standardkonto | 0 |  |
| 50100 | Hausmeister | 900 | nein | 010 | Standardkonto | 0 |  |
| 50110 | Hausreinigung | 900 | nein | 010 | Standardkonto | 0 |  |
| 50120 | Winterdienst | 900 | nein | 010 | Standardkonto | 0 |  |
| 50130 | Außenanlagen | 900 | nein | 010 | Standardkonto | 0 |  |
| 50200 | Straßenreinigung | 900 | nein | 010 | Standardkonto | 0 |  |
| 50210 | Niederschlagwasser | 900 | nein | 010 | Standardkonto | 0 |  |
| 50230 | Müllabfuhr | 900 | nein | 010 | Standardkonto | 0 |  |
| 50240 | Allgemeinstrom | 900 | nein | 010 | Standardkonto | 0 |  |
| 50299 | Heiz- und Wasserkosten nach Verbrauch | 900 | nein | 140 | Summierungskonto | 0 |  |
| 50300 | Wasser | 900 | nein |  | Unterkonto | Ja |  |
| 50310 | Abwasser | 900 | nein |  | Unterkonto | Ja |  |
| 50320 | Gas/Öl/Wärme | 900 | nein |  | Unterkonto | Ja |  |
| 50330 | Messdienst/Gerätemiete | 900 | nein |  | Unterkonto | Ja |  |
| 50340 | Heizungswartung | 900 | nein |  | Unterkonto | Ja |  |
| 50350 | Schornsteinfeger | 900 | nein |  | Unterkonto | Ja |  |
| 50360 | Heizungsstrom (aus Allgemeinstrom) | 900 | nein |  | Unterkonto | Ja |  |
| 50390 | Feuerstättenbescheid | 900 | nein | 010 | Standardkonto | 0 |  |
| 50400 | Betriebskosten Aufzug | 900 | nein | 010 | Standardkonto | 0 |  |
| 50500 | Wartung | 900 | nein | 010 | Standardkonto | 0 |  |
| 50510 | Wartung Brandschutz | 900 | nein | 010 | Standardkonto | 0 |  |
| 50520 | Wartung Wasser/Abwasseranlage | 900 | nein | 010 | Standardkonto | 0 |  |
| 50530 | Wartung Rolltor TG | 900 | nein | 010 | Standardkonto | 0 |  |
| 50540 | Wartung Dach/Rinnenreinigung | 900 | nein | 010 | Standardkonto | 0 |  |
| 50550 | Wartung Parker | 900 | nein | 010 | Standardkonto | 0 |  |
| 50560 | Wartung Rauchwarnmelder | 900 | nein | 010 | Standardkonto | 0 |  |
| 50590 | Schädlingsbekämpfung | 900 | nein | 010 | Standardkonto | 0 |  |
| 50600 | Kabelempfang | 900 | nein | 010 | Standardkonto | 0 |  |
| 50700 | Versicherungen | 900 | nein | 010 | Standardkonto | 0 |  |
| 50800 | Legionellenprüfung | 900 | nein | 010 | Standardkonto | 0 |  |
| 55100 | Verwaltergebühr Wohnung | 900 | nein | 031 | Standardkonto | 0 |  |
| 55110 | Verwaltergebühr Stellplätze | 900 | nein | 032 | Standardkonto | 0 |  |
| 55111 | Nichtteilnahme am Lastschriftverfahren | 900 | nein | 100 | Standardkonto | 0 |  |
| 55112 | Aufwand HNDL | 900 | nein | 030 | Standardkonto | 0 |  |
| 55113 | Abrechenbare Auslagen der Verwaltung | 900 | nein | 010 | Standardkonto | 0 |  |
| 55115 | Raummiete | 900 | nein | 010 | Standardkonto | 0 |  |
| 55200 | Reparaturen | 900 | nein | 010 | Standardkonto | 0 |  |
| 55210 | Instandsetzung Außenanlagen | 900 | nein | 010 | Standardkonto | 0 |  |
| 55290 | Reparatur VS | 900 | nein | 010 | Standardkonto | 0 |  |
| 55300 | Reparaturen Aufzug | 900 | nein | 010 | Standardkonto | 0 |  |
| 55350 | Sanierung | 900 | nein | 010 | Standardkonto | 0 |  |
| 55400 | Rechtskosten | 900 | nein | 010 | Standardkonto | 0 |  |
| 55410 | Beratungskosten | 900 | nein | 010 | Standardkonto | 0 |  |
| 55500 | Bankgebühren | 900 | nein | 010 | Standardkonto | 0 |  |
| 55900 | Direktkosten Eigentümer | 900 | nein | 101 | Standardkonto | 0 |  |
| 55905 | Mahngebühren | 900 | nein | 010 | Standardkonto | 0 |  |
| 57911 | Rücklage I | 911 | nein | 010 | Standardkonto | 0 |  |
| 90000 | Saldenvorträge Sachkonten |  | nein |  | Standardkonto | 0 |  |
| 90080 | Saldenvorträge Debitoren |  | nein |  | Standardkonto | 0 |  |
| 90090 | Saldenvorträge Kreditoren |  | nein |  | Standardkonto | 0 |  |
| 91000 | JA Buchung Vortrag Sachkonten |  | nein |  | Standardkonto | 0 |  |

### 6.2 `Abrechnungsarten.xlsx`

**Blatt `Tabelle1`** (6 Datenzeilen, 2 Spalten — Blatt ohne Kopfzeile)

| Spalte 1 | Spalte 2 |
|---|---|
| 900 | Hausgeld |
| 911 | Rücklage I |
| 930 | Sonderumlage |
| 940 | Mahngebühren |
| 941 | Rücklastschriftgebühren |
| 950 | Abrechnung Vorjahr |

### 6.3 `Verteilerschlüssel.xlsx`

**Blatt `Tabelle1`** (5 Datenzeilen, 2 Spalten — Blatt ohne Kopfzeile)

| Spalte 1 | Spalte 2 |
|---|---|
| 001 | Wohnfläche |
| 010 | MEA Gesamt |
| 030 | Anzahl Einheiten Gesamt |
| 031 | Anzahl Wohnungen |
| 032 | Anzahl Stellplätze |

---

## 7. Django-Admin-Registrierungen

Registriert: **29 Projekt-Modelle** (von insgesamt 87).

| Modell | list_display | list_filter | search_fields | Inlines | Actions | Rechte (add/change/delete) |
|---|---|---|---|---|---|---|
| `abrechnung_wp.Wirtschaftsplan` | `__str__` | — | — | — | — | Standard |
| `abrechnung_wp.WirtschaftsplanAnteil` | `__str__` | — | — | — | — | Standard |
| `abrechnung_wp.WirtschaftsplanPosition` | `__str__` | — | — | — | — | Standard |
| `buchhaltung.BankImport` | `buchungsdatum, betrag, auftraggeber_name, auftraggeber_iban, status, objekt` | `status, objekt, buchungsdatum` | `auftraggeber_name, auftraggeber_iban, verwendungszweck` | — | — | Standard |
| `buchhaltung.Buchung` | `buchungsdatum, betrag, status, objekt, belegnr, erstellt_von` | `status, objekt, buchungsdatum` | `belegnr, verwendungszweck` | — | — | Standard |
| `buchhaltung.EinzelAbrechnung` | `jahresabrechnung, einheit, hausgeld_soll_gesamt, kostenanteil_gesamt, abrechnungsergebnis, sollstellung` | `jahresabrechnung__objekt, jahresabrechnung__wirtschaftsjahr` | `einheit__einheit_nr` | — | — | Standard |
| `buchhaltung.Jahresabrechnung` | `wirtschaftsjahr, objekt, status, erstellungsdatum, erstellt_von` | `status, objekt, wirtschaftsjahr` | — | — | — | Standard |
| `dokumente.Dokument` | `dateiname, kategorie, objekt, einheit, hochgeladen_von, hochgeladen_am` | `kategorie, objekt` | `dateiname, kategorie, beschreibung` | — | — | Standard |
| `handwerker.Gewerk` | `bezeichnung, code, aktiv, sortierung` | `aktiv` | `code, bezeichnung` | — | — | Standard |
| `handwerker.Handwerkerauftrag` | `nummer, titel, objekt, kreditor, status, prioritaet` (+1) | `status, prioritaet, objekt` | `nummer, titel, kreditor__name, objekt__bezeichnung` | AuftragsbestaetigungsTokenInline, HandwerkerauftragEreignisInline | — | Standard |
| `handwerker.HandwerkerauftragEreignis` | `auftrag, typ, erstellt_am, erstellt_von` | `typ` | `auftrag__nummer, text` | — | — | add: False, chg: False, del: False |
| `handwerker.ObjektHandwerker` | `objekt, kreditor, prioritaet, erstellt_am` | `objekt` | `objekt__bezeichnung, kreditor__name` | — | — | Standard |
| `konten.Konto` | `kontonummer, kontoname, wirtschaftsjahr, kontoart, verteilerschluessel, umlagefaehig` (+1) | `kontoart, verteilerschluessel, umlagefaehig, aktiv, wirtschaftsjahr__objekt` | `kontonummer, kontoname` | — | — | Standard |
| `konten.Personenkonto` | `kontonummer, eigentuemer, objekt, status, archiviert_am` | `status, objekt` | `kontonummer, eigentuemer__nachname, eigentuemer__firmenname` | — | — | Standard |
| `konten.Unterkonto` | `volle_kontonummer, bezeichnung, personenkonto, suffix, bankkonto` | `personenkonto__objekt` | `bezeichnung, suffix` | — | — | Standard |
| `mitarbeiter.Mitarbeiter` | `__str__, telefon, aktiv, eingetreten_am` | `aktiv` | `user__first_name, user__last_name, user__email` | — | — | Standard |
| `objekte.Bankkonto` | `bezeichnung, objekt, konto_typ, iban, aktiv, reihenfolge` | `konto_typ, aktiv, objekt` | `bezeichnung, iban, kontoinhaber` | — | — | Standard |
| `objekte.Eingang` | `bezeichnung, objekt, strasse, ort` | `objekt` | `bezeichnung, strasse, ort` | — | — | Standard |
| `objekte.Einheit` | `einheit_nr, objekt, einheit_typ, lage` | `einheit_typ, objekt` | `einheit_nr, lage` | — | — | Standard |
| `objekte.Objekt` | `bezeichnung, objekt_typ, ort, status, verwaltung_seit` | `objekt_typ, status, umsatzsteuer_pflichtig` | `bezeichnung, strasse, ort, plz` | ObjektHandwerkerInline | — | Standard |
| `personen.EigentumsVerhaeltnis` | `person, einheit, beginn, ende, ist_aktiv` | `einheit__objekt` | `person__nachname, person__vorname, person__firmenname` | — | — | Standard |
| `personen.HausgeldHistorie` | `eigentumsverhaeltnis, betrag, gueltig_ab, erstellt_von` | `gueltig_ab` | `eigentumsverhaeltnis__person__nachname` | — | — | Standard |
| `personen.Mietvertrag` | `mieter, einheit, beginn, ende, kaltmiete` | `einheit__objekt` | `mieter__nachname, mieter__vorname, mieter__firmenname` | — | — | Standard |
| `personen.Person` | `name, person_typ, email, telefon, ist_firma` | `person_typ, ist_firma` | `vorname, nachname, firmenname, email` | — | — | Standard |
| `personen.SEPAMandat` | `mandatsreferenz, iban, unterzeichnet_am, aktiv` | `aktiv` | `mandatsreferenz, iban` | — | — | Standard |
| `prozesse.Prozess` | `prozess_typ, objekt, current_step, status, gestartet_von, gestartet_am` (+1) | `prozess_typ, status, objekt` | `objekt__bezeichnung, gestartet_von__username` | — | — | Standard |
| `rechnungen.Freigabe` | `rechnung, bearbeiter, rolle, entscheidung, zeitstempel` | `entscheidung, rolle` | `rechnung__rechnungsnummer, bearbeiter__username` | — | — | Standard |
| `rechnungen.Kreditor` | `name, kreditorennummer, gewerke_liste, ist_handwerker, aktiv, ort` | `gewerke, ist_handwerker, aktiv` | `name, kreditorennummer, iban, email` | — | — | Standard |
| `rechnungen.Rechnung` | `rechnungsnummer, lieferant, objekt, betrag_brutto, rechnungsdatum, faelligkeitsdatum` (+1) | `status, objekt, rechnungsdatum` | `rechnungsnummer, lieferant__nachname, lieferant__firmenname` | — | — | Standard |

Zusätzlich registriert (Django-eigene Apps): `auth.Group`, `auth.User`

**Nicht im Admin registriert (58):** `buchhaltung.AutoLaufProtokoll`, `buchhaltung.BankErkennungsLog`, `buchhaltung.BankMatchRegel`, `buchhaltung.Basiszinssatz`, `buchhaltung.Buchungsart`, `buchhaltung.Buchungsstapel`, `buchhaltung.CamtImportEinstellung`, `buchhaltung.CamtImportLog`, `buchhaltung.EigentuemerwechselVorgang`, `buchhaltung.Forderungsfall`, `buchhaltung.FrontofficeAufgabe`, `buchhaltung.HausgeldSollstellung`, `buchhaltung.HausgeldSollstellungslauf`, `buchhaltung.ImportOrdnerEinstellung`, `buchhaltung.Kontoumsatz`, `buchhaltung.KreditorOP`, `buchhaltung.LastschriftLauf`, `buchhaltung.Mahnlauf`, `buchhaltung.Mahnsperre`, `buchhaltung.Mahnung`, `buchhaltung.OffenerPosten`, `buchhaltung.OposSequenz`, `buchhaltung.RAPAufloesung`, `buchhaltung.RAPPosition`, `buchhaltung.SepaZahlungslauf`, `buchhaltung.SollstellungSplit`, `buchhaltung.SollstellungZahlung`, `buchhaltung.WechselKorrekturPaar`, `buchhaltung.WiederkehrendeBuchungOP`, `buchhaltung.WiederkehrendeBuchungSplit`, `buchhaltung.WiederkehrendeBuchungVorlage`, `buchhaltung.WirtschaftsplanBeschluss`, `buchhaltung.WirtschaftsplanKorrekturPaar`, `buchhaltung.WirtschaftsplanPosition`, `buchhaltung.WirtschaftsplanRuecklage`, `dokumente.BelegnummerZaehler`, `handwerker.AuftragsbestaetigungsToken`, `handwerker.HandwerkerauftragNummerZaehler`, `konten.Abrechnungsart`, `konten.KontoVerteilerSchluessel`, `massenimport.ImportJob`, `mitarbeiter.MitarbeiterObjektZuordnung`, `objekte.EinheitVerbrauch`, `objekte.VerteilerschluesselWert`, `objekte.Verteilerschluessel`, `objekte.Wirtschaftsjahr`, `rechnungen.FreigabelimitDefault`, `rechnungen.KreditorRegel`, `rechnungen.RechnungSplitPosition`, `rechnungen.RechnungsBearbeitungsLock`, `rechnungen.RechnungsErkennungsLog`, `rechnungen.RechnungsMatchRegel`, `rechnungen.Verarbeitungslog`, `vorgaenge.VorgangAntwortVorschlag`, `vorgaenge.VorgangEreignis`, `vorgaenge.VorgangNummerZaehler`, `vorgaenge.VorgangTyp`, `vorgaenge.Vorgang`

## 8. API: ViewSets, Permissions, URL-Präfixe

Gefunden: **69 View-Klassen** in `apps.*` über 550 URL-Routen.

| View-Klasse | Modul | URL-Präfix(e) | Permissions | Authentication | Throttle | Pagination |
|---|---|---|---|---|---|---|
| `WirtschaftsplanViewSet` | `apps.abrechnung_wp.views` | `/api/v1/^wirtschaftsplaene/$/`, `/api/v1/^wirtschaftsplaene/(?P/`, `/api/v1/^wirtschaftsplaene\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `AutoLaufProtokollViewSet` | `apps.buchhaltung.views` | `/api/v1/^auto-lauf-protokolle/$/`, `/api/v1/^auto-lauf-protokolle/(?P/`, `/api/v1/^auto-lauf-protokolle/einstellungen/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BankImportViewSet` | `apps.buchhaltung.views` | `/api/v1/^bank-importe/$/`, `/api/v1/^bank-importe/(?P/`, `/api/v1/^bank-importe/camt053-upload/$/` (+6) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BankMatchRegelViewSet` | `apps.buchhaltung.views` | `/api/v1/^e-banking/bank-match-regeln/$/`, `/api/v1/^e-banking/bank-match-regeln/(?P/`, `/api/v1/^e-banking/bank-match-regeln\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BasiszinssatzViewSet` | `apps.buchhaltung.views` | `/api/v1/^basiszinssaetze/$/`, `/api/v1/^basiszinssaetze/(?P/`, `/api/v1/^basiszinssaetze/aktuell/$/` (+4) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BuchungViewSet` | `apps.buchhaltung.views` | `/api/v1/^buchungen/$/`, `/api/v1/^buchungen/(?P/`, `/api/v1/^buchungen/export-csv/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BuchungsartViewSet` | `apps.buchhaltung.views` | `/api/v1/^buchungsarten/$/`, `/api/v1/^buchungsarten/(?P/`, `/api/v1/^buchungsarten/manuell-waehlbar/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BuchungsstapelViewSet` | `apps.buchhaltung.views` | `/api/v1/^buchungsstapel/$/`, `/api/v1/^buchungsstapel/(?P/`, `/api/v1/^buchungsstapel\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `CamtImportEinstellungViewSet` | `apps.buchhaltung.views` | `/api/v1/^camt-einstellungen/$/`, `/api/v1/^camt-einstellungen/(?P/`, `/api/v1/^camt-einstellungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `CamtImportLogViewSet` | `apps.buchhaltung.views` | `/api/v1/^camt-logs/$/`, `/api/v1/^camt-logs/(?P/`, `/api/v1/^camt-logs\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `EBankingBuchungViewSet` | `apps.buchhaltung.views` | `/api/v1/^e-banking/bank-buchungen/$/`, `/api/v1/^e-banking/bank-buchungen/(?P/`, `/api/v1/^e-banking/bank-buchungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `EinzelAbrechnungViewSet` | `apps.buchhaltung.views` | `/api/v1/^einzelabrechnungen/$/`, `/api/v1/^einzelabrechnungen/(?P/`, `/api/v1/^einzelabrechnungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `ForderungsfallViewSet` | `apps.buchhaltung.views` | `/api/v1/^forderungsfaelle/$/`, `/api/v1/^forderungsfaelle/(?P/`, `/api/v1/^forderungsfaelle\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `HausgeldSollstellungViewSet` | `apps.buchhaltung.views` | `/api/v1/^hg-sollstellungen/$/`, `/api/v1/^hg-sollstellungen/(?P/`, `/api/v1/^hg-sollstellungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `HausgeldSollstellungslaufViewSet` | `apps.buchhaltung.views` | `/api/v1/^hg-laeufe/$/`, `/api/v1/^hg-laeufe/(?P/`, `/api/v1/^hg-laeufe/erstellen/$/` (+6) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `ImportOrdnerEinstellungViewSet` | `apps.buchhaltung.views` | `/api/v1/^import-ordner/$/`, `/api/v1/^import-ordner/(?P/`, `/api/v1/^import-ordner\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `JahresabrechnungViewSet` | `apps.buchhaltung.views` | `/api/v1/^jahresabrechnungen/$/`, `/api/v1/^jahresabrechnungen/(?P/`, `/api/v1/^jahresabrechnungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `KontoumsatzViewSet` | `apps.buchhaltung.views` | `/api/v1/^kontoumsaetze/$/`, `/api/v1/^kontoumsaetze/(?P/`, `/api/v1/^kontoumsaetze/camt-upload/$/` (+10) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `KreditorOPViewSet` | `apps.buchhaltung.views` | `/api/v1/^e-banking/kreditor-ops/$/`, `/api/v1/^e-banking/kreditor-ops/(?P/`, `/api/v1/^e-banking/kreditor-ops\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `LastschriftLaufViewSet` | `apps.buchhaltung.views` | `/api/v1/^lastschrift-laeufe/$/`, `/api/v1/^lastschrift-laeufe/(?P/`, `/api/v1/^lastschrift-laeufe\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MahnlaufViewSet` | `apps.buchhaltung.views` | `/api/v1/^mahnlaeufe/$/`, `/api/v1/^mahnlaeufe/(?P/`, `/api/v1/^mahnlaeufe/simulieren/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MahnsperreViewSet` | `apps.buchhaltung.views` | `/api/v1/^mahnsperren/$/`, `/api/v1/^mahnsperren/(?P/`, `/api/v1/^mahnsperren\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MahnungViewSet` | `apps.buchhaltung.views` | `/api/v1/^mahnungen/$/`, `/api/v1/^mahnungen/(?P/`, `/api/v1/^mahnungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `OffenerPostenViewSet` | `apps.buchhaltung.views` | `/api/v1/^offene-posten/$/`, `/api/v1/^offene-posten/(?P/`, `/api/v1/^offene-posten\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `RAPAufloesungViewSet` | `apps.buchhaltung.views` | `/api/v1/^rap-aufloesungen/$/`, `/api/v1/^rap-aufloesungen/(?P/`, `/api/v1/^rap-aufloesungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `RAPPositionViewSet` | `apps.buchhaltung.views` | `/api/v1/^rap-positionen/$/`, `/api/v1/^rap-positionen/(?P/`, `/api/v1/^rap-positionen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `SepaZahlungslaufViewSet` | `apps.buchhaltung.views` | `/api/v1/^sepa-zahlungslaeufe/$/`, `/api/v1/^sepa-zahlungslaeufe/(?P/`, `/api/v1/^sepa-zahlungslaeufe\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `WirtschaftsjahrViewSet` | `apps.buchhaltung.views` | `/api/v1/^wirtschaftsjahre/$/`, `/api/v1/^wirtschaftsjahre/(?P/`, `/api/v1/^wirtschaftsjahre/folgejahr/commit/$/` (+4) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `KreditorWKZVorlagenViewSet` | `apps.buchhaltung.views_wkz` | `/api/v1/kreditoren/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `WKZForecastViewSet` | `apps.buchhaltung.views_wkz` | `/api/v1/objekte/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `WKZOPViewSet` | `apps.buchhaltung.views_wkz` | `/api/v1/^wkz-ops/$/`, `/api/v1/^wkz-ops/(?P/`, `/api/v1/^wkz-ops/sepa-export/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `WKZVorlageViewSet` | `apps.buchhaltung.views_wkz` | `/api/v1/^wkz-vorlagen/$/`, `/api/v1/^wkz-vorlagen/(?P/`, `/api/v1/^wkz-vorlagen\.(?P/` (+1) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `DokumentViewSet` | `apps.dokumente.views` | `/api/v1/^dokumente/$/`, `/api/v1/^dokumente/(?P/`, `/api/v1/^dokumente\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `GewerkAdminViewSet` | `apps.handwerker.views` | `/api/v1/^gewerke/admin/$/`, `/api/v1/^gewerke/admin/(?P/`, `/api/v1/^gewerke/admin\.(?P/` | IsAdminUser | JWTAuthentication, SessionAuthentication | — | — |
| `GewerkViewSet` | `apps.handwerker.views` | `/api/v1/^gewerke/$/`, `/api/v1/^gewerke/(?P/`, `/api/v1/^gewerke\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `HandwerkerauftragViewSet` | `apps.handwerker.views` | `/api/v1/^handwerkerauftraege/$/`, `/api/v1/^handwerkerauftraege/(?P/`, `/api/v1/^handwerkerauftraege\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | HandwerkerauftragPagination |
| `ObjektHandwerkerViewSet` | `apps.handwerker.views` | `/api/v1/^objekt-handwerker/$/`, `/api/v1/^objekt-handwerker/(?P/`, `/api/v1/^objekt-handwerker\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `OeffentlicherAuftragBestaetigenView` | `apps.handwerker.views_oeffentlich` | `/api/v1/oeffentlich/auftrag/` | AllowAny | [] (bewusst leer) | ScopedRateThrottle | — |
| `OeffentlicherAuftragDetailView` | `apps.handwerker.views_oeffentlich` | `/api/v1/oeffentlich/auftrag/` | AllowAny | [] (bewusst leer) | ScopedRateThrottle | — |
| `AbrechnungsartViewSet` | `apps.konten.views` | `/api/v1/^abrechnungsarten/$/`, `/api/v1/^abrechnungsarten/(?P/`, `/api/v1/^abrechnungsarten\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `KontoViewSet` | `apps.konten.views` | `/api/v1/^konten/$/`, `/api/v1/^konten/(?P/`, `/api/v1/^konten/bebuchte/$/` (+4) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `PersonenkontoViewSet` | `apps.konten.views` | `/api/v1/^personenkonten/$/`, `/api/v1/^personenkonten/(?P/`, `/api/v1/^personenkonten/mit-saldo/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `UnterkontoViewSet` | `apps.konten.views` | `/api/v1/^unterkonten/$/`, `/api/v1/^unterkonten/(?P/`, `/api/v1/^unterkonten\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `commit_weg` | `apps.massenimport.views` | `/api/v1/massenimport/weg/commit/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `job_status` | `apps.massenimport.views` | `/api/v1/massenimport/jobs/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `preview_weg` | `apps.massenimport.views` | `/api/v1/massenimport/weg/preview/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `vorlage_weg` | `apps.massenimport.views` | `/api/v1/massenimport/vorlage/weg/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MitarbeiterObjektZuordnungViewSet` | `apps.mitarbeiter.views` | `/api/v1/^mitarbeiter-zuordnungen/$/`, `/api/v1/^mitarbeiter-zuordnungen/(?P/`, `/api/v1/^mitarbeiter-zuordnungen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MitarbeiterViewSet` | `apps.mitarbeiter.views` | `/api/v1/^mitarbeiter/$/`, `/api/v1/^mitarbeiter/(?P/`, `/api/v1/^mitarbeiter\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `BankkontoViewSet` | `apps.objekte.views` | `/api/v1/^bankkonten/$/`, `/api/v1/^bankkonten/(?P/`, `/api/v1/^bankkonten\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `EingangViewSet` | `apps.objekte.views` | `/api/v1/^eingaenge/$/`, `/api/v1/^eingaenge/(?P/`, `/api/v1/^eingaenge\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `EinheitViewSet` | `apps.objekte.views` | `/api/v1/^einheiten/$/`, `/api/v1/^einheiten/(?P/`, `/api/v1/^einheiten/csv-import/$/` (+6) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `ObjektViewSet` | `apps.objekte.views` | `/api/v1/^objekte/$/`, `/api/v1/^objekte/(?P/`, `/api/v1/^objekte\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `VerteilerschluesselViewSet` | `apps.objekte.views` | `/api/v1/^verteilerschluessel/$/`, `/api/v1/^verteilerschluessel/(?P/`, `/api/v1/^verteilerschluessel\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `VerteilerschluesselWertViewSet` | `apps.objekte.views` | `/api/v1/^verteilerschluessel-werte/$/`, `/api/v1/^verteilerschluessel-werte/(?P/`, `/api/v1/^verteilerschluessel-werte\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `EigentumsVerhaeltnisViewSet` | `apps.personen.views` | `/api/v1/^eigentumsverhaeltnisse/$/`, `/api/v1/^eigentumsverhaeltnisse/(?P/`, `/api/v1/^eigentumsverhaeltnisse\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `HausgeldHistorieViewSet` | `apps.personen.views` | `/api/v1/^hausgeld-historie/$/`, `/api/v1/^hausgeld-historie/(?P/`, `/api/v1/^hausgeld-historie\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `MietvertragViewSet` | `apps.personen.views` | `/api/v1/^mietvertraege/$/`, `/api/v1/^mietvertraege/(?P/`, `/api/v1/^mietvertraege\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `PersonViewSet` | `apps.personen.views` | `/api/v1/^personen/$/`, `/api/v1/^personen/(?P/`, `/api/v1/^personen/csv-import/$/` (+6) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `SEPAMandatViewSet` | `apps.personen.views` | `/api/v1/^sepa-mandate/$/`, `/api/v1/^sepa-mandate/(?P/`, `/api/v1/^sepa-mandate\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `ProzessViewSet` | `apps.prozesse.views` | `/api/v1/^prozesse/$/`, `/api/v1/^prozesse/(?P/`, `/api/v1/^prozesse\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `FreigabeViewSet` | `apps.rechnungen.views` | `/api/v1/^freigaben/$/`, `/api/v1/^freigaben/(?P/`, `/api/v1/^freigaben\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `FreigabelimitDefaultView` | `apps.rechnungen.views` | `/api/v1/freigabelimits-standard/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `KreditorViewSet` | `apps.rechnungen.views` | `/api/v1/^kreditoren/$/`, `/api/v1/^kreditoren/(?P/`, `/api/v1/^kreditoren/duplikat-pruefen/$/` (+2) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `RechnungViewSet` | `apps.rechnungen.views` | `/api/v1/^rechnungen/$/`, `/api/v1/^rechnungen/(?P/`, `/api/v1/^rechnungen/erfassen/$/` (+10) | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `RechnungsMatchRegelViewSet` | `apps.rechnungen.views` | `/api/v1/^match-regeln/$/`, `/api/v1/^match-regeln/(?P/`, `/api/v1/^match-regeln\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `VorgangTypAdminViewSet` | `apps.vorgaenge.views` | `/api/v1/^vorgang-typen/admin/$/`, `/api/v1/^vorgang-typen/admin/(?P/`, `/api/v1/^vorgang-typen/admin\.(?P/` | IsAdminUser | JWTAuthentication, SessionAuthentication | — | — |
| `VorgangTypViewSet` | `apps.vorgaenge.views` | `/api/v1/^vorgang-typen/$/`, `/api/v1/^vorgang-typen/(?P/`, `/api/v1/^vorgang-typen\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |
| `VorgangViewSet` | `apps.vorgaenge.views` | `/api/v1/^vorgaenge/$/`, `/api/v1/^vorgaenge/(?P/`, `/api/v1/^vorgaenge\.(?P/` | IsAuthenticated | JWTAuthentication, SessionAuthentication | — | — |

### 8.1 Globale DRF-Konfiguration

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication', 'rest_framework.authentication.SessionAuthentication'),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_THROTTLE_RATES': {'auftrag_token': '30/hour'},
}
```

---

*Ende des Exports.*
