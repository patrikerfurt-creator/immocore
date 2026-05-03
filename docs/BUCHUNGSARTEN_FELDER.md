# Buchungsart — Feldbeschreibung

Jede Buchungsart (BA) steuert über ihre Felder, wie eine Buchung vom System behandelt wird:
ob sie in Abrechnungen erscheint, ob sie einen Beleg erfordert, ob sie manuell gebucht
werden darf und auf welche Konten sie defaultmäßig zeigt.

---

## nr
**Typ:** Text (3 Zeichen), eindeutig

Dreistellige Ordnungsnummer des BA-Katalogs. Dient der stabilen Referenzierung im Code
und in Exporten. Beispiel: `040` = SACH-A.

---

## kuerzel
**Typ:** Text (max. 12 Zeichen)

Kurzbezeichnung für die Oberfläche und Auswertungen. Beispiel: `SACH-A`, `HGV`, `EING-K`.

---

## bezeichnung
**Typ:** Text (max. 120 Zeichen)

Ausgeschriebener Name der Buchungsart, wie er in Listen, Journalen und Belegen angezeigt
wird. Beispiel: `Sachkontenbuchung Aufwand (Bewirtschaftung)`.

---

## einzelabrechnung
**Typ:** Auswahl — `ja` / `nein` / `anteilig`

Steuert, ob Buchungen dieser Art in der **Einzelabrechnung** des jeweiligen Eigentümers
erscheinen. Die Einzelabrechnung ist das persönliche Abrechnungsblatt, das jeder
Wohnungseigentümer am Jahresende erhält.

| Wert | Bedeutung |
|------|-----------|
| `ja` | Buchung fließt vollständig in die Einzelabrechnung ein und wird nach Miteigentumsanteil (MEA) auf die Eigentümer verteilt |
| `nein` | Buchung erscheint nicht in der Einzelabrechnung (z.B. reine Zahlungseingänge, Saldenvorträge) |
| `anteilig` | Nur ein definierter Teilbetrag wird umgelegt — für Sonderfälle vorgesehen, aktuell nicht aktiv genutzt |

Beispiele: HGV (`ja`), SACH-A (`ja`), EING-P (`nein`), SAVO-S (`nein`)

---

## gesamtabrechnung
**Typ:** Boolean (True / False)

Steuert, ob Buchungen dieser Art in der **Gesamtabrechnung der WEG** erscheinen.
Die Gesamtabrechnung zeigt alle Einnahmen und Ausgaben des Objekts auf Sachkontoebene
und wird in der Eigentümerversammlung beschlossen.

| Wert | Bedeutung |
|------|-----------|
| `True` | Buchung fließt in die WEG-Jahresabrechnung ein (Aufwände, Erträge, Sollstellungen) |
| `False` | Buchung bleibt buchhalterisch intern — nicht abrechnungsrelevant (Zahlungen, Umbuchungen, Saldenvorträge) |

Faustregel: Alles was in die GuV / den Wirtschaftsplan einfließt, hat `True`.

---

## ruecklagen_relevant
**Typ:** Boolean (True / False)

Kennzeichnet Buchungen, die die **Instandhaltungsrücklage** (Konto .911) betreffen.
Solche Buchungen werden bei der Rücklagenentwicklung und im Rücklagenspiegel
gesondert ausgewiesen.

| Wert | Bedeutung |
|------|-----------|
| `True` | Buchung berührt die Rücklage — erscheint im Rücklagenspiegel (z.B. RLZ, SACH-AR, SACH-ER, RL-ENT) |
| `False` | Kein Rücklagenbezug |

---

## umlage
**Typ:** Auswahl — `pflicht` / `optional` / `gesperrt`

Steuert, ob eine Buchung dieser Art im Rahmen der **Jahresabrechnung auf Eigentümer
umgelegt** werden darf bzw. muss.

| Wert | Bedeutung |
|------|-----------|
| `pflicht` | Muss umgelegt werden — Betrag wird zwingend auf Eigentümer verteilt (z.B. reguläre Bewirtschaftungskosten SACH-A, Sonderumlage SU) |
| `optional` | Kann umgelegt werden — Entscheidung liegt beim Sachbearbeiter (z.B. bestimmte Erträge, EING-K) |
| `gesperrt` | Darf nicht umgelegt werden — systeminterne oder neutrale Buchung (Zahlungen, Saldenvorträge, Mahngebühren) |

---

## beleg_pflicht
**Typ:** Boolean (True / False)

Gibt an, ob beim Erfassen einer Buchung dieser Art ein **Belegdokument** (Rechnung,
Kontoauszug etc.) hinterlegt werden muss.

| Wert | Bedeutung |
|------|-----------|
| `True` | Buchung kann nur mit Beleg gespeichert werden — Pflichtfeld in der Buchungsmaske |
| `False` | Kein Beleg erforderlich (z.B. Zahlungseingänge die per CAMT automatisch importiert werden) |

---

## beschluss_pflicht
**Typ:** Boolean (True / False)

Gibt an, ob vor dem Buchen ein **Eigentümerbeschluss** vorliegen muss.
Betrifft Buchungsarten mit besonderer rechtlicher Tragweite nach WEG.

| Wert | Bedeutung |
|------|-----------|
| `True` | System prüft, ob ein verknüpfter Beschluss existiert — ohne Beschluss wird die Buchung abgelehnt (z.B. Sonderumlage SU, Rücklagenaufwand SACH-AR) |
| `False` | Kein Beschluss erforderlich |

---

## vier_augen_schwelle
**Typ:** Dezimalzahl (€), nullable

Betragslimit für das **Vier-Augen-Prinzip**. Buchungen dieser Art, deren Betrag die
Schwelle überschreitet, müssen von einer zweiten Person freigegeben werden.

| Wert | Bedeutung |
|------|-----------|
| Betrag (z.B. `10000.00`) | Ab diesem Betrag ist eine zweite Freigabe erforderlich |
| leer (`null`) | Kein Vier-Augen-Prinzip für diese Buchungsart |

Aktuell gesetzte Schwellen:
- SU (Sonderumlage): 5.000 €
- SACH-A (Aufwand Bewirtschaftung): 10.000 €
- SACH-AR (Aufwand Rücklage): 5.000 €

---

## sperre_nach_jahresabschluss
**Typ:** Boolean (True / False)

Verhindert nachträgliche Buchungen im abgeschlossenen Wirtschaftsjahr.

| Wert | Bedeutung |
|------|-----------|
| `True` | Buchungen dieser Art können nach Jahresabschluss nicht mehr im alten Jahr erfasst werden — schützt die Abschlussperiode |
| `False` | Auch nach Jahresabschluss noch buchbar im alten Jahr (z.B. Zahlungseingänge, die technisch noch zuzuordnen sind) |

---

## system_buchungsart
**Typ:** Boolean (True / False)

Kennzeichnet Buchungsarten, die **ausschließlich durch automatische Systemprozesse**
erzeugt werden dürfen und in der manuellen Buchungsmaske nicht auswählbar sind.

| Wert | Bedeutung |
|------|-----------|
| `True` | Nur durch Systemprozesse buchbar: Sollstellungsläufe, Jahresabschluss-Routinen, Mahnwesen-Automatik (z.B. SAVO-*, HGV, JA-ABS) |
| `False` | Manuell durch Sachbearbeiter wählbar |

---

## default_konto_soll_pattern
**Typ:** Text, optional

Kontopattern für die **Soll-Seite** der Buchung. Das Pattern ist ein Teilstring
des Kontonummernschemas (z.B. `.911` für Rücklagenkonto). Wird beim automatischen
Vorbelegen des Kontofeldes in der Buchungsmaske und in Systemprozessen verwendet.

Leer = kein Default-Soll-Konto definiert.

---

## default_konto_haben_pattern
**Typ:** Text, optional

Kontopattern für die **Haben-Seite** der Buchung — analog zu `default_konto_soll_pattern`.

Beispiel: `SACH-AR` hat Haben-Pattern `.911` → die Haben-Seite zeigt immer auf das
Rücklagenkonto des Objekts.

---

## aktiv
**Typ:** Boolean (True / False)

Gibt an, ob die Buchungsart **in der Anwendung verfügbar** ist.

| Wert | Bedeutung |
|------|-----------|
| `True` | Buchungsart ist aktiv und kann verwendet werden |
| `False` | Deaktiviert — erscheint nicht in Auswahllisten, kann nicht neu gebucht werden. Bestehende Buchungen bleiben erhalten |
