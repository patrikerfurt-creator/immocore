# Korrespondenz — Mapping der bisherigen Word-Seriendruckfelder

Quelle: Spec `CLAUDE_CODE_ANLEITUNG_VORLAGEN_KORRESPONDENZ_v1_2.md`, Anhang C.

Damit Mitarbeiter ihre bisherigen Word-Vorlagen wiedererkennen und bestehende Vorlagen später
übertragen werden können. Im Vorlagentext steht ein Platzhalter als `{{ gruppe.name }}`,
optional mit Filter (`{{ schreiben.datum | datum_mittel }}`). Die vollständige Liste aller
Platzhalter je Anlass steht in [`korrespondenz_platzhalter.md`](korrespondenz_platzhalter.md).

| Bisheriges Feld | Neuer Platzhalter | Hinweis |
|---|---|---|
| `EmpfAnsZeile1`–`7` | `empfaenger.anschrift_zeilen` | Der Briefbogen setzt die Zeilen automatisch ins Anschriftfeld (höchstens 7 Zeilen). Im Fließtext nicht nötig. |
| `EmpfAnredePers1` / `2` | `empfaenger.briefanrede` / `empfaenger.briefanrede2` | Die Anrede setzt der Briefbogen selbst unter den Betreff; `briefanrede2` ist bei Einzelpersonen leer. |
| `PerObjNrPerNr` | `schreiben.unser_zeichen` | **Annahme:** `objekt.objektnummer` + `/` + `Personenkonto.kontonummer`. Patrik bestätigt das Format. Steht automatisch in der Bezugszeichenzeile („Unser Zeichen"). |
| `AktDatumLang` | `schreiben.datum \| datum_mittel` | Ergibt z. B. „29. September 2026". Steht automatisch in der Bezugszeichenzeile („Datum"). Mit `datum_lang` mit Wochentag, mit `datum` als 29.09.2026. |
| `ObjNr` / `ObjBez` | `objekt.objektnummer` / `objekt.bezeichnung` | Die Zeile „Objekt: Nummer-Bezeichnung" setzt der Briefbogen selbst. |
| `FlNr` / `FlBez` | `einheit.flaechennummer` / `einheit.lage` | Die Zeile „Fläche: Nummer-Lage" setzt der Briefbogen selbst; sie entfällt ohne Einheit. |
| `UserVorname` / `UserNachname` | `verwaltung.unterzeichner_vorname` / `verwaltung.unterzeichner_nachname` | Der Briefbogen setzt „gez. Vorname Nachname" unter die Grußformel. |
| `ObjPerÜbBnkIBAN` | `bank.iban` | Jetzt über das mit Sachkonto 18000 verknüpfte Bankkonto des Objekts. Mit Filter `iban` in Vierergruppen: `{{ bank.iban \| iban }}`. |

## Was der Briefbogen automatisch liefert

In den Vorlagentext gehören nur Betreff und Inhalt. Diese Teile kommen vom Briefbogen und
müssen nicht (mehr) als Feld in die Vorlage:

- Briefkopf, Logo, Absenderzeile und Infoblock (Firma, Adresse, Telefon, Sprechzeiten)
- Anschriftfeld (`empfaenger.anschrift_zeilen`)
- Bezugszeichenzeile: Ihr Zeichen, Ihr Schreiben vom, Unser Zeichen, Datum
- Objekt- und Flächenzeile über dem Betreff
- Briefanrede
- Grußformel mit Firmenname und „gez. Vorname Nachname"
- Fußzeile mit Bankverbindung des Objekts (bei WEG-Objekten)

## Filter

| Filter | Wirkung | Beispiel |
|---|---|---|
| `datum` | Datum numerisch | 29.09.2026 |
| `datum_mittel` | Datum ausgeschrieben | 29. September 2026 |
| `datum_lang` | Datum mit Wochentag | Dienstag, den 29. September 2026 |
| `uhrzeit` | Uhrzeit | 16.00 Uhr |
| `euro` | Betrag | 1.234,56 € |
| `iban` | IBAN in Vierergruppen | DE02 5019 0000 6300 2110 10 |
| `upper` | Großbuchstaben | |
| `default` | Ersatzwert bei leerem Platzhalter | |
