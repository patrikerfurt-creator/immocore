# Korrespondenz — Platzhalter

> Generiert aus der Platzhalter-Registry (`apps/korrespondenz/services/registry.py`) mit `python manage.py erzeuge_platzhalter_doku`. Nicht von Hand ändern.

Im Vorlagentext werden Platzhalter als `{{ gruppe.name }}` geschrieben, optional mit Filtern (`{{ mahnung.frist | datum }}`). Filter: `euro`, `datum`, `datum_lang`, `datum_mittel`, `uhrzeit`, `iban`, `upper`, `default`.

Die Gruppe `eingabe` ist dynamisch: sie enthält die Eingabefelder der jeweiligen Vorlagenversion (`{{ eingabe.<feldname> }}`) und ist deshalb hier nicht aufgelistet.

## Anlass `eigentuemer_begruessung`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `hausgeld`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `hausgeld.monatsbetrag` | Monatliches Hausgeld gesamt | betrag | `350.00` |
| `hausgeld.gueltig_ab` | Hausgeld gültig ab | datum | `2026-09-01` |
| `hausgeld.positionen` | Tabelle der Hausgeld-Positionen | tabelle | `[{"bezeichnung": "Hausgeld", "betrag": "300.00"}, {"bezeichnung": "Rücklage",...` |

### Gruppe `wechsel`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `wechsel.wechsel_datum` | Datum des Eigentümerwechsels | datum | `2026-09-01` |
| `wechsel.voreigentuemer_name` | Name des Voreigentümers | text | `Hans Alt` |

## Anlass `eigentuemer_verabschiedung`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `wechsel`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `wechsel.wechsel_datum` | Datum des Eigentümerwechsels | datum | `2026-09-01` |
| `wechsel.voreigentuemer_name` | Name des Voreigentümers | text | `Hans Alt` |

## Anlass `mahnung_stufe_1`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `mahnung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `mahnung.stufe` | Mahnstufe (Wert von Mahnung.mahnstufe) | zahl | `1` |
| `mahnung.offene_posten` | Tabelle der offenen Posten | tabelle | `[{"faellig_ab": "2026-08-01", "bezeichnung": "Hausgeld 08/2026", "betrag_ursp...` |
| `mahnung.summe_hauptforderung` | Summe der offenen Hauptforderung | betrag | `350.00` |
| `mahnung.gebuehr` | Mahngebühr | betrag | `5.00` |
| `mahnung.zinsen` | Verzugszinsen | betrag | `1.20` |
| `mahnung.gesamtbetrag` | Hauptforderung + Gebühr + Zinsen | betrag | `356.20` |
| `mahnung.frist` | Zahlungsfrist (Mahnlauf-Datum + Frist der Stufe, nächster Werktag) | datum | `2026-10-13` |
| `mahnung.zinssatz` | Verzugszinssatz (Basiszinssatz + 5 Prozentpunkte) | text | `8,62 %` |
| `mahnung.basiszinssatz` | Basiszinssatz | text | `3,62 %` |

## Anlass `mahnung_stufe_2`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `mahnung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `mahnung.stufe` | Mahnstufe (Wert von Mahnung.mahnstufe) | zahl | `1` |
| `mahnung.offene_posten` | Tabelle der offenen Posten | tabelle | `[{"faellig_ab": "2026-08-01", "bezeichnung": "Hausgeld 08/2026", "betrag_ursp...` |
| `mahnung.summe_hauptforderung` | Summe der offenen Hauptforderung | betrag | `350.00` |
| `mahnung.gebuehr` | Mahngebühr | betrag | `5.00` |
| `mahnung.zinsen` | Verzugszinsen | betrag | `1.20` |
| `mahnung.gesamtbetrag` | Hauptforderung + Gebühr + Zinsen | betrag | `356.20` |
| `mahnung.frist` | Zahlungsfrist (Mahnlauf-Datum + Frist der Stufe, nächster Werktag) | datum | `2026-10-13` |
| `mahnung.zinssatz` | Verzugszinssatz (Basiszinssatz + 5 Prozentpunkte) | text | `8,62 %` |
| `mahnung.basiszinssatz` | Basiszinssatz | text | `3,62 %` |

## Anlass `mahnung_stufe_3`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `mahnung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `mahnung.stufe` | Mahnstufe (Wert von Mahnung.mahnstufe) | zahl | `1` |
| `mahnung.offene_posten` | Tabelle der offenen Posten | tabelle | `[{"faellig_ab": "2026-08-01", "bezeichnung": "Hausgeld 08/2026", "betrag_ursp...` |
| `mahnung.summe_hauptforderung` | Summe der offenen Hauptforderung | betrag | `350.00` |
| `mahnung.gebuehr` | Mahngebühr | betrag | `5.00` |
| `mahnung.zinsen` | Verzugszinsen | betrag | `1.20` |
| `mahnung.gesamtbetrag` | Hauptforderung + Gebühr + Zinsen | betrag | `356.20` |
| `mahnung.frist` | Zahlungsfrist (Mahnlauf-Datum + Frist der Stufe, nächster Werktag) | datum | `2026-10-13` |
| `mahnung.zinssatz` | Verzugszinssatz (Basiszinssatz + 5 Prozentpunkte) | text | `8,62 %` |
| `mahnung.basiszinssatz` | Basiszinssatz | text | `3,62 %` |

## Anlass `etv_einladung`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

### Gruppe `versammlung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `versammlung.termin` | Termin der Versammlung (Datum und Uhrzeit, Ortszeit; Filter datum_lang / uhrzeit) | datum | `2026-12-18T16:00:00` |
| `versammlung.ort` | Versammlungsort | text | `Achat Hotel Offenbach, Ernst-Griesheimer-Platz 7 in 63071 Offenbach` |
| `versammlung.tagesordnung` | Titel der Tagesordnungspunkte in Reihenfolge | liste | `["Beschlussfassung über die Jahresabrechnung 2025", "Beschlussfassung über de...` |
| `versammlung.art` | Art der Versammlung als Adjektiv („eine … Eigentümerversammlung“) | text | `ordentliche` |

## Anlass `eigentuemer_allgemein`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `ev`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `ev.beginn` | Beginn des Eigentumsverhältnisses | datum | `2026-09-01` |
| `ev.sepa_mandat_vorhanden` | Aktives SEPA-Mandat liegt vor | bool | `False` |
| `ev.sepa_mandat_fehlt` | Kein aktives SEPA-Mandat | bool | `True` |

## Anlass `vorgang_antwort`

### Gruppe `empfaenger`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `empfaenger.anschrift_zeilen` | Anschriftfeld, höchstens 7 Zeilen | liste | `["Eheleute", "Dr. Max Mustermann", "Erika Mustermann", "Musterweg 5", "60311 ...` |
| `empfaenger.briefanrede` | Briefanrede (1. Person) | text | `Sehr geehrte Frau Mustermann,` |
| `empfaenger.briefanrede2` | Briefanrede 2. Person (leer bei Einzelperson) | text | `sehr geehrter Herr Mustermann,` |
| `empfaenger.name` | Name des Empfängers | text | `Dr. Max und Erika Mustermann` |
| `empfaenger.personennummer` | Personennummer | text | `100123` |

### Gruppe `objekt`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `objekt.objektnummer` | Objektnummer | text | `53` |
| `objekt.bezeichnung` | Bezeichnung des Objekts | text | `WEG Musterstraße 1` |
| `objekt.anschrift` | Anschrift des Objekts | text | `Musterstraße 1, 60311 Frankfurt am Main` |
| `objekt.ist_weg` | Objekt ist eine WEG | bool | `True` |

### Gruppe `einheit`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `einheit.einheit_nr` | Einheitennummer | text | `12` |
| `einheit.flaechennummer` | Flächennummer | text | `0012` |
| `einheit.lage` | Lage der Einheit | text | `Wohnung 2. OG links` |
| `einheit.typ` | Einheitentyp | text | `Wohnung` |

### Gruppe `schreiben`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `schreiben.unser_zeichen` | Unser Zeichen: Objektnummer/Personenkontonummer | text | `53/0012` |
| `schreiben.ihr_zeichen` | Ihr Zeichen (optional, kann leer sein) | text | — |
| `schreiben.ihr_schreiben_vom` | Ihr Schreiben vom (optional) | datum | `2026-09-01` |
| `schreiben.datum` | Schreibensdatum | datum | `2026-09-29` |
| `schreiben.nummer` | Schreibennummer | text | `KS-2026-000123` |

### Gruppe `verwaltung`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `verwaltung.firma` | Name der Verwaltungsfirma (Briefbogen) | text | `Demme Immobilien Verwaltung GmbH` |
| `verwaltung.unterzeichner_vorname` | Vorname des Unterzeichners | text | `Patrik` |
| `verwaltung.unterzeichner_nachname` | Nachname des Unterzeichners | text | `Maurer` |
| `verwaltung.betreuer_name` | Name des Objektbetreuers | text | `Anna Beispiel` |
| `verwaltung.betreuer_telefon` | Telefon des Objektbetreuers | text | `069-96 75 20 90` |
| `verwaltung.betreuer_email` | E-Mail des Objektbetreuers | text | `a.beispiel@demme-immobilien.de` |

### Gruppe `bank`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `bank.weg_name` | Name der WEG (Objektbezeichnung) | text | `WEG Musterstraße 1` |
| `bank.iban` | IBAN des Zahlungsverkehrskontos | text | `DE00 0000 0000 0000 0000 00` |
| `bank.bic` | BIC des Zahlungsverkehrskontos | text | `TESTDEFFXXX` |
| `bank.bankname` | Name der Bank (aus der IBAN abgeleitet, schwifty) | text | `Testbank` |
| `bank.kontoinhaber` | Kontoinhaber | text | `WEG Musterstraße 1` |
| `bank.glaeubiger_id` | Gläubiger-ID des Objekts | text | `DE98ZZZ09999999999` |

### Gruppe `vorgang`

| Platzhalter | Beschreibung | Typ | Beispiel |
|---|---|---|---|
| `vorgang.nummer` | Vorgangsnummer | text | `V-2026-000042` |
| `vorgang.betreff` | Betreff des Vorgangs | text | `Schaden im Treppenhaus` |
