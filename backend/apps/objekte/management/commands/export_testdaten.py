"""
Management-Command: export_testdaten
Exportiert Einheiten, Personen und Verträge eines Objekts als Import-fähige CSV-Dateien.

Aufruf:
    python manage.py export_testdaten
    python manage.py export_testdaten --objekt 10003
    python manage.py export_testdaten --objekt 10003 --output C:\\Pfad\\zum\\Ordner
"""

import csv
import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from apps.objekte.models import Objekt, Einheit
from apps.personen.models import Person, EigentumsVerhaeltnis


EINHEIT_TYP_CODE = {
    'Wohnung': '100',
    'Gewerbe': '200',
    'Stellplatz': '300',
    'Sonstiges': '400',
}


def _datum_de(d) -> str:
    """date → DD.MM.YYYY"""
    if not d:
        return ''
    return d.strftime('%d.%m.%Y')


def _betrag_de(d) -> str:
    """Decimal → deutsche Darstellung: 474.25 → '474,25'"""
    if d is None:
        return ''
    return str(d).replace('.', ',')


class Command(BaseCommand):
    help = 'Exportiert Einheiten, Personen und Verträge eines Objekts als Import-CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            '--objekt',
            default='10003',
            help='Objektnummer (Standard: 10003)',
        )
        parser.add_argument(
            '--output',
            default=None,
            help='Ausgabe-Verzeichnis (Standard: Testdateine IMPORT im Projektstamm)',
        )

    def handle(self, *args, **options):
        objektnummer = options['objekt']

        if options['output']:
            output_dir = options['output']
        else:
            # Projektstamm = zwei Ebenen über manage.py (backend/)
            manage_dir = os.path.dirname(os.path.abspath(__file__))
            # commands/ -> management/ -> objekte/ -> apps/ -> backend/ -> immocore/
            projekt_root = os.path.normpath(
                os.path.join(manage_dir, '..', '..', '..', '..', '..')
            )
            output_dir = os.path.join(projekt_root, 'Testdateine IMPORT')

        os.makedirs(output_dir, exist_ok=True)

        try:
            objekt = Objekt.objects.get(objektnummer=objektnummer)
        except Objekt.DoesNotExist:
            raise CommandError(f'Objekt "{objektnummer}" nicht gefunden')

        self.stdout.write(f'\nObjekt {objektnummer}: {objekt.bezeichnung}')
        self.stdout.write(f'Ausgabe-Verzeichnis: {output_dir}\n')

        einheiten_path = os.path.join(output_dir, f'{objektnummer}-Einheiten.csv')
        personen_path = os.path.join(output_dir, f'{objektnummer}-Personen.csv')
        vertraege_path = os.path.join(output_dir, f'{objektnummer}-Vertraege.csv')

        n_einheiten = self._export_einheiten(objekt, einheiten_path)
        n_personen = self._export_personen(objekt, personen_path)
        n_vertraege = self._export_vertraege(objekt, vertraege_path)

        self.stdout.write(self.style.SUCCESS('\nFertig - Dateien erstellt:'))
        self.stdout.write(f'  {n_einheiten:>3} Einheiten  ->  {einheiten_path}')
        self.stdout.write(f'  {n_personen:>3} Personen   ->  {personen_path}')
        self.stdout.write(f'  {n_vertraege:>3} Vertraege  ->  {vertraege_path}')
        self.stdout.write('')

    # ------------------------------------------------------------------
    # Einheiten
    # ------------------------------------------------------------------
    def _export_einheiten(self, objekt, path):
        einheiten = (
            Einheit.objects
            .filter(objekt=objekt)
            .select_related('eingang')
            .order_by('flaechennummer', 'einheit_nr')
        )

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['# Einheit-Typ: 100=Wohnung | 200=Gewerbe | 300=Stellplatz | 400=Sonstiges'])
            writer.writerow(['Objektnummer', 'Eingang', 'Flächennummer', 'Bez. Einheit', 'Einheit-Typ', 'Lage'])
            for e in einheiten:
                eingang_bez = e.eingang.strasse if e.eingang else ''
                writer.writerow([
                    objekt.objektnummer,
                    eingang_bez,
                    e.flaechennummer or '',
                    e.einheit_nr,
                    EINHEIT_TYP_CODE.get(e.einheit_typ, '400'),
                    e.lage or '',
                ])

        count = einheiten.count()
        self.stdout.write(f'  Einheiten exportiert: {count}')
        return count

    # ------------------------------------------------------------------
    # Personen
    # ------------------------------------------------------------------
    def _export_personen(self, objekt, path):
        personen = (
            Person.objects
            .filter(eigentumsverhaeltnisse__einheit__objekt=objekt)
            .distinct()
            .order_by('personennummer')
        )

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['# person_typ: 100=Eigentümer | 200=Mieter | 300=Kreditor | 400=Sonstiges'])
            writer.writerow(['# Anrede-Werte: Herr | Frau | Eheleute | Herren | Damen | Herr und Frau | Firma'])
            writer.writerow([
                'person_typ', 'ist_firma', 'Firma',
                'Anrede', 'Anrede1', 'Vorname1', 'Nachname1',
                'Anrede2', 'Vorname2', 'Nachname2',
                'Anschrift', 'PLZ', 'Ort', 'Email1', 'Email2', 'IBAN',
            ])

            for p in personen:
                anschrift, plz, ort = _split_adresse(p.adresse)
                vorname1, nachname1, anrede1, vorname2, nachname2, anrede2 = _split_namen(p)
                iban = p.ibans[0] if p.ibans else ''

                writer.writerow([
                    p.person_typ,
                    'TRUE' if p.ist_firma else 'FALSE',
                    p.firmenname if p.ist_firma else '',
                    p.anrede,
                    anrede1,
                    vorname1,
                    nachname1,
                    anrede2,
                    vorname2,
                    nachname2,
                    anschrift,
                    plz,
                    ort,
                    p.email,
                    '',
                    iban,
                ])

        count = personen.count()
        self.stdout.write(f'  Personen exportiert:  {count}')
        return count

    # ------------------------------------------------------------------
    # Verträge (EigentumsVerhältnisse + HausgeldHistorie)
    # ------------------------------------------------------------------
    def _export_vertraege(self, objekt, path):
        einheiten = (
            Einheit.objects
            .filter(objekt=objekt)
            .order_by('flaechennummer', 'einheit_nr')
        )
        evs = (
            EigentumsVerhaeltnis.objects
            .filter(einheit__objekt=objekt, ende__isnull=True)
            .select_related('person')
            .prefetch_related('hausgeld_historie')
        )
        ev_by_einheit = {str(ev.einheit_id): ev for ev in evs}
        heute = date.today()

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                'Fl Nr. ', 'Personnummer', 'ET ab',
                'SA1', 'Betrag1', 'SA1 ab',
                'SA2', 'Betrag2', 'SA2 ab',
                'SA3', 'Betrag3', 'SA3 ab',
                'SA4', 'Betrag4', 'SA4 ab',
                'SA5', 'Betrag5', 'SA5 ab',
                'SA6', 'Betrag6', 'SA6 ab',
                'SA7', 'Betrag7', 'SA7 ab',
            ])

            for einheit in einheiten:
                ev = ev_by_einheit.get(str(einheit.id))
                row = [einheit.flaechennummer or '']

                if ev:
                    row.append(ev.person.personennummer)
                    row.append(_datum_de(ev.beginn))

                    # Neueste Beträge pro Kontoart (gueltig_ab <= heute)
                    latest = (
                        ev.hausgeld_historie
                        .filter(gueltig_ab__lte=heute)
                        .values('kontoart')
                        .annotate(max_datum=Max('gueltig_ab'))
                        .order_by('kontoart')
                    )
                    sollarten = []
                    for art in latest:
                        eintrag = ev.hausgeld_historie.filter(
                            kontoart=art['kontoart'],
                            gueltig_ab=art['max_datum'],
                        ).first()
                        if eintrag:
                            kontoart_csv = art['kontoart'].lstrip('.')  # '.900' → '900'
                            sollarten.append((
                                kontoart_csv,
                                _betrag_de(eintrag.betrag),
                                _datum_de(art['max_datum']),
                            ))

                    for i in range(7):
                        row.extend(sollarten[i] if i < len(sollarten) else ['', '', ''])
                else:
                    row.extend(['', ''])
                    row.extend(['', '', ''] * 7)

                writer.writerow(row)

        count = einheiten.count()
        self.stdout.write(f'  Verträge exportiert:  {count} Zeilen')
        return count


# ------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------

def _split_adresse(adresse: str) -> tuple[str, str, str]:
    """'Musterstr. 1\n60001 Frankfurt' → ('Musterstr. 1', '60001', 'Frankfurt')"""
    lines = (adresse or '').splitlines()
    anschrift = lines[0].strip() if lines else ''
    plz_ort = lines[1].strip() if len(lines) > 1 else ''
    parts = plz_ort.split(' ', 1)
    plz = parts[0] if parts else ''
    ort = parts[1] if len(parts) > 1 else ''
    return anschrift, plz, ort


def _split_namen(p: Person) -> tuple[str, str, str, str, str, str]:
    """
    Gibt (vorname1, nachname1, anrede1, vorname2, nachname2, anrede2) zurück.
    Für Eheleute wird versucht, den zusammengesetzten Vornamen aufzuspalten.
    """
    # Neu importierte Personen haben ggf. vorname2/nachname2 direkt gesetzt
    if p.vorname2 or p.nachname2:
        return (
            p.vorname, p.nachname, p.anrede,
            p.vorname2, p.nachname2, '',
        )

    ist_paar = p.anrede in ('Eheleute', 'Herr und Frau', 'Herren', 'Damen')
    if ist_paar and ' und ' in p.vorname:
        parts = p.vorname.split(' und ', 1)
        vorname1 = parts[0].strip()
        vorname2 = parts[1].strip()
        anrede1 = 'Frau' if p.anrede in ('Eheleute', 'Herr und Frau') else p.anrede
        anrede2 = 'Herr' if p.anrede in ('Eheleute', 'Herr und Frau') else ''
        return (
            vorname1, p.nachname, anrede1,
            vorname2, p.nachname, anrede2,
        )

    return p.vorname, p.nachname, p.anrede, '', '', ''
