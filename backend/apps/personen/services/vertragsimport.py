"""
Vertragsmanagement-CSV-Import (Spec v1.1)

SA-Format vertikal (Semikolon, UTF-8-BOM) — eine Zeile je SA-Eintrag:
  Fl Nr.;Personnummer;ET ab;SA;Betrag;SA ab

SA-Format horizontal (Altsystem, Rückwärtskompatibilität):
  Fl Nr.;Personnummer;ET ab;SA1;Betrag1;SA1 ab;SA2;Betrag2;SA2 ab;...

IMMOCORE-Standardformat:
  einheit_nr;flaechennummer;personennummer;eigentuemer_email;vertrag_beginn;vertrag_ende;
  abrechnungsart;betrag;gueltig_ab;wirtschaftsplan_jahr;bemerkung

Ablauf: parse_csv → vorschau → commit (atomar)
"""
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

logger = logging.getLogger(__name__)

PFLICHT_SPALTEN = {
    'einheit_nr', 'eigentuemer_email', 'vertrag_beginn', 'vertrag_ende',
    'abrechnungsart', 'betrag', 'gueltig_ab', 'wirtschaftsplan_jahr', 'bemerkung',
}
MAX_GROESSE_BYTES = 5 * 1024 * 1024   # 5 MB
MAX_ZEILEN = 10_000


class ImportFehler(Exception):
    pass


@dataclass
class ZeilenErgebnis:
    zeilennummer: int
    einheit_nr: str
    abrechnungsart: str
    gueltig_ab: str
    betrag: str
    wirtschaftsplan_jahr: int | None
    aktion: str           # 'neu' | 'aktualisiert' | 'bestehend_unveraendert' | 'vertrag_neu' | 'fehler'
    status: str           # 'ok' | 'warnung' | 'fehler'
    meldungen: list = field(default_factory=list)
    historie_id: str | None = None


@dataclass
class ImportErgebnis:
    status: str           # 'ok' | 'fehler'
    meldung: str | None
    zeilen: list
    zusammenfassung: dict = field(default_factory=dict)


SA_SPALTEN_PFLICHT = {'Personnummer', 'ET ab'}

def _decode_bytes(datei_bytes: bytes) -> tuple[str, list[str]]:
    """Dekodiert bytes und gibt (content, lines_ohne_kommentare) zurück."""
    if len(datei_bytes) > MAX_GROESSE_BYTES:
        raise ImportFehler('Datei überschreitet 5 MB.')
    content = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            content = datei_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise ImportFehler('Datei-Encoding nicht erkennbar. Bitte als UTF-8 mit BOM speichern.')
    lines = [l.rstrip() for l in content.splitlines()]
    lines = [l for l in lines if l and not l.startswith('#')]
    if not lines:
        raise ImportFehler('Datei ist leer oder enthält nur Kommentare.')
    if ';' not in lines[0]:
        raise ImportFehler('Trennzeichen muss Semikolon (;) sein.')
    return content, lines


def _ist_sa_format(lines: list[str]) -> bool:
    """Gibt True zurück wenn die Datei das SA-Altsystemformat hat."""
    if not lines:
        return False
    header_cols = {c.strip() for c in lines[0].split(';')}
    return bool(SA_SPALTEN_PFLICHT & header_cols)


def _parse_csv_sa_format(lines: list[str]) -> list[dict]:
    """
    Parst das SA-Format in zwei Varianten:

    Vertikal (neu): Fl Nr.;Personnummer;ET ab;SA;Betrag;SA ab
      → eine Zeile je SA-Eintrag

    Horizontal (Altsystem): Fl Nr.;Personnummer;ET ab;SA1;Betrag1;SA1 ab;...
      → eine Zeile je Einheit, bis zu 7 SA-Tripel

    Erkennung: Vertikales Format hat die Spalte 'SA' (ohne Ziffernindex).
    """
    reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]

    vertikal = 'SA' in (reader.fieldnames or [])

    ergebnis: list[dict] = []
    for row in reader:
        fl_nr = row.get('Fl Nr.', '').strip()
        personnummer = row.get('Personnummer', '').strip()
        et_ab_str = row.get('ET ab', '').strip()

        if not fl_nr:
            continue

        vertrag_beginn = _parse_datum(et_ab_str)
        vertrag_beginn_iso = vertrag_beginn.isoformat() if vertrag_beginn else ''

        if vertikal:
            tripel = [(
                row.get('SA', '').strip(),
                row.get('Betrag', '').strip(),
                row.get('SA ab', '').strip(),
            )]
        else:
            tripel = [
                (row.get(f'SA{i}', '').strip(),
                 row.get(f'Betrag{i}', '').strip(),
                 row.get(f'SA{i} ab', '').strip())
                for i in range(1, 8)
            ]

        for abr, betrag_raw, gueltig_ab_str in tripel:
            if not abr or not betrag_raw or not gueltig_ab_str:
                continue

            gueltig_ab = _parse_datum(gueltig_ab_str)
            gueltig_ab_iso = gueltig_ab.isoformat() if gueltig_ab else ''

            wp_jahr = ''
            if gueltig_ab and gueltig_ab.month == 1 and gueltig_ab.day == 1:
                wp_jahr = str(gueltig_ab.year)

            ergebnis.append({
                'einheit_nr':                fl_nr,
                'einheit_flaechennummer':    fl_nr,
                'eigentuemer_email':         '',
                'eigentuemer_personennummer': personnummer,
                'vertrag_beginn':            vertrag_beginn_iso,
                'vertrag_ende':              '',
                'abrechnungsart':            abr,
                'betrag':                    betrag_raw.replace(',', '.'),
                'gueltig_ab':                gueltig_ab_iso,
                'wirtschaftsplan_jahr':      wp_jahr,
                'bemerkung':                 '',
            })

    if len(ergebnis) > MAX_ZEILEN:
        raise ImportFehler(f'Datei enthält mehr als {MAX_ZEILEN} Zeilen.')
    return ergebnis


def parse_csv(datei_bytes: bytes) -> list[dict]:
    """
    Liest CSV (UTF-8-BOM, Semikolon). Erkennt automatisch Standard- und SA-Format.
    Gibt Liste von Row-Dicts zurück.
    Wirft ImportFehler bei Schema-Problemen.
    """
    _, lines = _decode_bytes(datei_bytes)

    if _ist_sa_format(lines):
        return _parse_csv_sa_format(lines)

    # Standard-Format (IMMOCORE-Vorlage)
    reader = csv.DictReader(io.StringIO('\n'.join(lines)), delimiter=';')
    spalten = set(reader.fieldnames or [])
    fehlend = PFLICHT_SPALTEN - spalten
    if fehlend:
        raise ImportFehler(f"Fehlende Spalten: {', '.join(sorted(fehlend))}")

    zeilen = list(reader)
    if len(zeilen) > MAX_ZEILEN:
        raise ImportFehler(f'Datei enthält mehr als {MAX_ZEILEN} Zeilen.')

    # personennummer-Spalte → eigentuemer_personennummer mappen
    if 'personennummer' in spalten:
        for z in zeilen:
            if not z.get('eigentuemer_personennummer'):
                z['eigentuemer_personennummer'] = z.get('personennummer', '').strip()

    return zeilen


def _parse_datum(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # Deutsches Format DD.MM.YYYY
    try:
        d, m, y = s.split('.')
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _parse_betrag(s: str) -> Decimal | None:
    s = s.strip().replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _zeilen_key(zeile: dict) -> tuple:
    return (
        zeile.get('einheit_nr', '').strip(),
        zeile.get('abrechnungsart', '').strip(),
        zeile.get('gueltig_ab', '').strip(),
    )


def _resolve_einheit(einheit_nr: str, einheiten_map: dict, flaechenmap: dict):
    """Sucht Einheit zuerst per einheit_nr, dann per flaechennummer."""
    return einheiten_map.get(einheit_nr) or flaechenmap.get(einheit_nr)


def _resolve_person(email: str, personennummer: str):
    """Sucht Person per Email, Fallback auf Personennummer (auch wenn im E-Mail-Feld eingetragen)."""
    from apps.personen.models import Person
    if email:
        person = Person.objects.filter(email=email).first()
        if person:
            return person
        # Personennummer wurde möglicherweise ins E-Mail-Feld eingetragen
        person = Person.objects.filter(personennummer=email).first()
        if person:
            return person
    if personennummer:
        return Person.objects.filter(personennummer=personennummer).first()
    return None


def vorschau(zeilen_roh: list[dict], objekt) -> list[ZeilenErgebnis]:
    """
    Validiert alle Zeilen gegen DB und CSV-intern.
    Keine DB-Änderungen.
    """
    from apps.objekte.models import Einheit
    from apps.konten.models import Abrechnungsart
    from apps.personen.models import EigentumsVerhaeltnis

    einheiten_map = {
        e.einheit_nr: e
        for e in Einheit.objects.filter(objekt=objekt)
    }
    flaechenmap = {
        e.flaechennummer: e
        for e in Einheit.objects.filter(objekt=objekt)
        if e.flaechennummer
    }
    abr_map = {
        a.code: a
        for a in Abrechnungsart.objects.filter(objekt=objekt, aktiv=True)
    }

    ergebnisse: list[ZeilenErgebnis] = []
    gesehene_keys: set = set()

    for i, z in enumerate(zeilen_roh, start=2):
        einheit_nr     = z.get('einheit_nr', '').strip()
        email          = z.get('eigentuemer_email', '').strip()
        personennummer = z.get('eigentuemer_personennummer', '').strip()
        beginn_str     = z.get('vertrag_beginn', '').strip()
        ende_str       = z.get('vertrag_ende', '').strip()
        abr_code       = z.get('abrechnungsart', '').strip()
        betrag_str     = z.get('betrag', '').strip()
        gueltig_ab_str = z.get('gueltig_ab', '').strip()
        wp_jahr_str    = z.get('wirtschaftsplan_jahr', '').strip()
        bemerkung      = z.get('bemerkung', '').strip()

        meldungen: list[str] = []
        status = 'ok'
        aktion = 'neu'

        def fehler(msg: str):
            nonlocal status, aktion
            meldungen.append(msg)
            status = 'fehler'
            aktion = 'fehler'

        def warnung(msg: str):
            nonlocal status
            meldungen.append(msg)
            if status == 'ok':
                status = 'warnung'

        # Pflichtfelder
        if not einheit_nr:
            fehler('Pflichtfeld einheit_nr fehlt')
        if not beginn_str:
            fehler('Pflichtfeld vertrag_beginn fehlt')
        if not abr_code:
            fehler('Pflichtfeld abrechnungsart fehlt')
        if not betrag_str:
            fehler('Pflichtfeld betrag fehlt')
        if not gueltig_ab_str:
            fehler('Pflichtfeld gueltig_ab fehlt')

        if status == 'fehler':
            ergebnisse.append(ZeilenErgebnis(
                zeilennummer=i, einheit_nr=einheit_nr, abrechnungsart=abr_code,
                gueltig_ab=gueltig_ab_str, betrag=betrag_str,
                wirtschaftsplan_jahr=None, aktion=aktion, status=status, meldungen=meldungen,
            ))
            continue

        # Einheit prüfen (einheit_nr oder flaechennummer)
        einheit = _resolve_einheit(einheit_nr, einheiten_map, flaechenmap)
        if not einheit:
            fehler(f"Einheit '{einheit_nr}' nicht gefunden")

        # Abrechnungsart prüfen
        if abr_code == '910':
            fehler('Suffix .910 ist gesperrt')
        elif abr_code not in abr_map:
            fehler(f"Abrechnungsart '{abr_code}' nicht am Objekt definiert")

        # Datumsfelder
        beginn = _parse_datum(beginn_str)
        if not beginn:
            fehler(f'vertrag_beginn ungültig: {beginn_str}')

        ende = None
        if ende_str:
            ende = _parse_datum(ende_str)
            if not ende:
                fehler(f'vertrag_ende ungültig: {ende_str}')

        gueltig_ab = _parse_datum(gueltig_ab_str)
        if not gueltig_ab:
            fehler(f'gueltig_ab ungültig: {gueltig_ab_str}')

        if beginn and gueltig_ab and gueltig_ab < beginn:
            fehler('gueltig_ab darf nicht vor Vertragsbeginn liegen')

        if ende and gueltig_ab and gueltig_ab > ende:
            fehler('gueltig_ab liegt nach Vertragsende')

        # Betrag
        betrag = _parse_betrag(betrag_str)
        if betrag is None:
            fehler(f'Betrag ungültig: {betrag_str}')
        elif betrag < 0:
            fehler('Betrag muss >= 0 sein')
        elif betrag == 0 and abr_code == '900':
            warnung('Hausgeld 0,00 — vermutlich Eingabefehler')

        # wirtschaftsplan_jahr
        wp_jahr = None
        if wp_jahr_str:
            try:
                wp_jahr = int(wp_jahr_str)
            except ValueError:
                fehler(f'wirtschaftsplan_jahr ungültig: {wp_jahr_str}')

        if gueltig_ab:
            if not wp_jahr_str and gueltig_ab.month == 1 and gueltig_ab.day == 1:
                warnung(f'Tipp: WP-Jahr {gueltig_ab.year} eintragen')
            if wp_jahr and gueltig_ab and wp_jahr != gueltig_ab.year:
                warnung(f'WP-Jahr {wp_jahr} weicht von gueltig_ab-Jahr {gueltig_ab.year} ab — bitte prüfen')
            if gueltig_ab > date.today().replace(year=date.today().year + 2):
                warnung(f'Eintrag für {gueltig_ab} weit in der Zukunft — prüfen')

        # Doppelte Zeile in CSV
        key = _zeilen_key(z)
        if key in gesehene_keys:
            fehler(f'Doppelte Zeile für {einheit_nr}/{abr_code}/{gueltig_ab_str}')
        gesehene_keys.add(key)

        if status == 'fehler':
            ergebnisse.append(ZeilenErgebnis(
                zeilennummer=i, einheit_nr=einheit_nr, abrechnungsart=abr_code,
                gueltig_ab=gueltig_ab_str, betrag=betrag_str,
                wirtschaftsplan_jahr=wp_jahr, aktion=aktion, status=status, meldungen=meldungen,
            ))
            continue

        # Aktiven Vertrag suchen / Neuanlage prüfen
        if einheit:
            aktiver_ev = EigentumsVerhaeltnis.objects.filter(
                einheit=einheit, ende__isnull=True
            ).first()

            if aktiver_ev and aktiver_ev.beginn == beginn:
                # Bestehender Vertrag
                aktion_ev = 'bestehend'
            elif aktiver_ev and aktiver_ev.beginn != beginn:
                fehler(
                    f'Aktiver Vertrag für {einheit_nr} hat Beginn {aktiver_ev.beginn}, '
                    f'CSV liefert {beginn}. Eigentümerwechsel über dedizierten Wizard.'
                )
            elif not aktiver_ev:
                # Neuanlage
                if not email and not personennummer:
                    fehler(f'Einheit {einheit_nr}: kein aktiver Vertrag — eigentuemer_email oder Personnummer erforderlich')
                else:
                    person_check = _resolve_person(email, personennummer)
                    if person_check:
                        aktion_ev = 'neu'
                    else:
                        kennung = email or personennummer
                        fehler(
                            f"Person '{kennung}' nicht in Stammdaten. "
                            f'Bitte zuerst Eigentümer-Import durchführen.'
                        )
            else:
                aktion_ev = 'bestehend'

        if status == 'fehler':
            ergebnisse.append(ZeilenErgebnis(
                zeilennummer=i, einheit_nr=einheit_nr, abrechnungsart=abr_code,
                gueltig_ab=gueltig_ab_str, betrag=betrag_str,
                wirtschaftsplan_jahr=wp_jahr, aktion=aktion, status=status, meldungen=meldungen,
            ))
            continue

        # Bestehendes HausgeldHistorie-Objekt prüfen (Aktion bestimmen)
        if einheit and aktion != 'fehler':
            from apps.personen.models import HausgeldHistorie
            ev = EigentumsVerhaeltnis.objects.filter(einheit=einheit, ende__isnull=True).first()
            if ev and abr_code in abr_map:
                bestehend = HausgeldHistorie.objects.filter(
                    eigentumsverhaeltnis=ev,
                    abrechnungsart=abr_map[abr_code],
                    gueltig_ab=gueltig_ab,
                ).first()
                if bestehend:
                    if (
                        bestehend.betrag == betrag
                        and bestehend.wirtschaftsplan_jahr == wp_jahr
                        and bestehend.bemerkung == bemerkung
                    ):
                        aktion = 'bestehend_unveraendert'
                        meldungen.append('Bestehender Eintrag — keine Änderung')
                        if status == 'ok':
                            status = 'ok'
                    else:
                        aktion = 'aktualisiert'
                else:
                    aktion = 'vertrag_neu' if aktion_ev == 'neu' else 'neu'

        ergebnisse.append(ZeilenErgebnis(
            zeilennummer=i, einheit_nr=einheit_nr, abrechnungsart=abr_code,
            gueltig_ab=gueltig_ab_str, betrag=betrag_str,
            wirtschaftsplan_jahr=wp_jahr, aktion=aktion, status=status, meldungen=meldungen,
        ))

    return ergebnisse


@transaction.atomic
def commit(zeilen_roh: list[dict], objekt, user) -> ImportErgebnis:
    """
    Importiert alle Zeilen atomar. Bei einem Fehler wird die gesamte Transaktion zurückgerollt.
    """
    from apps.objekte.models import Einheit
    from apps.konten.models import Abrechnungsart
    from apps.personen.models import EigentumsVerhaeltnis, HausgeldHistorie, Person
    from apps.konten.services import personenkonto_anlegen

    einheiten_map = {
        e.einheit_nr: e
        for e in Einheit.objects.filter(objekt=objekt)
    }
    flaechenmap = {
        e.flaechennummer: e
        for e in Einheit.objects.filter(objekt=objekt)
        if e.flaechennummer
    }
    abr_map = {
        a.code: a
        for a in Abrechnungsart.objects.filter(objekt=objekt, aktiv=True)
    }

    ergebnisse: list[ZeilenErgebnis] = []
    gesehene_keys: set = set()
    zaehler = {'neu': 0, 'aktualisiert': 0, 'unveraendert': 0, 'vertraege_neu': 0}

    for i, z in enumerate(zeilen_roh, start=2):
        einheit_nr     = z.get('einheit_nr', '').strip()
        email          = z.get('eigentuemer_email', '').strip()
        personennummer = z.get('eigentuemer_personennummer', '').strip()
        beginn_str     = z.get('vertrag_beginn', '').strip()
        ende_str       = z.get('vertrag_ende', '').strip()
        abr_code       = z.get('abrechnungsart', '').strip()
        betrag_str     = z.get('betrag', '').strip()
        gueltig_ab_str = z.get('gueltig_ab', '').strip()
        wp_jahr_str    = z.get('wirtschaftsplan_jahr', '').strip()
        bemerkung      = z.get('bemerkung', '').strip()

        # Basis-Validierung (wirft Exception bei kritischen Fehlern)
        einheit = _resolve_einheit(einheit_nr, einheiten_map, flaechenmap)
        if not einheit:
            raise ImportFehler(f'Zeile {i}: Einheit "{einheit_nr}" nicht gefunden')

        abr = abr_map.get(abr_code)
        if not abr:
            raise ImportFehler(f'Zeile {i}: Abrechnungsart "{abr_code}" nicht am Objekt')

        beginn = _parse_datum(beginn_str)
        if not beginn:
            raise ImportFehler(f'Zeile {i}: vertrag_beginn ungültig: {beginn_str}')

        ende = _parse_datum(ende_str) if ende_str else None

        gueltig_ab = _parse_datum(gueltig_ab_str)
        if not gueltig_ab:
            raise ImportFehler(f'Zeile {i}: gueltig_ab ungültig: {gueltig_ab_str}')

        betrag = _parse_betrag(betrag_str)
        if betrag is None or betrag < 0:
            raise ImportFehler(f'Zeile {i}: Betrag ungültig: {betrag_str}')

        wp_jahr = int(wp_jahr_str) if wp_jahr_str.isdigit() else None

        key = (einheit_nr, abr_code, gueltig_ab_str)
        if key in gesehene_keys:
            raise ImportFehler(f'Zeile {i}: Doppelte Zeile für {einheit_nr}/{abr_code}/{gueltig_ab_str}')
        gesehene_keys.add(key)

        # Vertrag auflösen / anlegen
        ev = EigentumsVerhaeltnis.objects.filter(einheit=einheit, ende__isnull=True).first()
        vertrag_neu = False

        if ev and ev.beginn == beginn:
            pass  # bestehender Vertrag, ok
        elif ev and ev.beginn != beginn:
            raise ImportFehler(
                f'Zeile {i}: Aktiver Vertrag für {einheit_nr} hat Beginn {ev.beginn}, '
                f'CSV liefert {beginn}.'
            )
        else:
            # Neuanlage
            if not email and not personennummer:
                raise ImportFehler(f'Zeile {i}: Neuanlage benötigt eigentuemer_email oder Personnummer')
            person = _resolve_person(email, personennummer)
            if not person:
                kennung = email or personennummer
                raise ImportFehler(f'Zeile {i}: Person "{kennung}" nicht gefunden')

            ev = EigentumsVerhaeltnis.objects.create(
                einheit=einheit, person=person, beginn=beginn, ende=ende,
            )
            personenkonto_anlegen(ev, objekt)
            vertrag_neu = True
            zaehler['vertraege_neu'] += 1

        # Historieneintrag idempotent anlegen
        defaults = {
            'betrag':               betrag,
            'wirtschaftsplan_jahr': wp_jahr,
            'bemerkung':            bemerkung,
            'quelle':               'import',
            'import_referenz':      'csv_import',
            'erstellt_von':         user,
        }
        hist, created = HausgeldHistorie.objects.update_or_create(
            eigentumsverhaeltnis=ev,
            abrechnungsart=abr,
            gueltig_ab=gueltig_ab,
            defaults=defaults,
        )

        if vertrag_neu:
            aktion = 'vertrag_neu'
            zaehler['neu'] += 1
        elif created:
            aktion = 'neu'
            zaehler['neu'] += 1
        else:
            aktion = 'aktualisiert'
            zaehler['aktualisiert'] += 1

        ergebnisse.append(ZeilenErgebnis(
            zeilennummer=i, einheit_nr=einheit_nr, abrechnungsart=abr_code,
            gueltig_ab=gueltig_ab_str, betrag=betrag_str, wirtschaftsplan_jahr=wp_jahr,
            aktion=aktion, status='ok', meldungen=[],
            historie_id=str(hist.id),
        ))

    return ImportErgebnis(
        status='ok',
        meldung=None,
        zeilen=ergebnisse,
        zusammenfassung={
            'zeilen_gesamt':              len(ergebnisse),
            'zeilen_ok':                  len(ergebnisse),
            'zeilen_fehler':              0,
            'vertraege_neu':              zaehler['vertraege_neu'],
            'vertraege_bestehend':        len({z.einheit_nr for z in ergebnisse}) - zaehler['vertraege_neu'],
            'historie_eintraege_neu':     zaehler['neu'],
            'historie_eintraege_aktualisiert': zaehler['aktualisiert'],
        },
    )
