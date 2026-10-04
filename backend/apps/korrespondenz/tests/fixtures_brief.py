"""Testdaten für Briefbogen und PDF (Phase 3, Anhang B der Spec).

Bewusst kein Seed: Der Standard-Briefbogen samt DB-Verknüpfung der Logos ist
Phase 7. Hier entstehen Briefbogen und Logo-``Dokument`` nur für Tests bzw. die
Demo (Aufrufer sorgt für ein temporäres ``MEDIA_ROOT``).
"""
from datetime import date
from pathlib import Path

from django.core.files.base import ContentFile

from apps.dokumente.models import Dokument
from apps.korrespondenz.models import Briefbogen, Vorlage, VorlagenVersion
from apps.korrespondenz.services import kontext_service

ASSETS = Path(__file__).resolve().parent.parent / 'assets'

ANHANG_B_IBAN = 'DE00 0000 0000 0000 0000 00'
ANHANG_B_BIC = 'TESTDEFFXXX'

EINGABEFELDER = [
    {'name': 'versammlung_datum', 'label': 'Datum der Versammlung', 'typ': 'datum', 'pflicht': True},
    {'name': 'versammlung_uhrzeit', 'label': 'Uhrzeit', 'typ': 'uhrzeit', 'pflicht': True},
    {'name': 'versammlung_ort', 'label': 'Ort / Adresse', 'typ': 'mehrzeilig', 'pflicht': True},
    {'name': 'tagesordnung', 'label': 'Tagesordnungspunkte', 'typ': 'liste', 'pflicht': True},
    {'name': 'art', 'label': 'Art', 'typ': 'text', 'pflicht': False, 'default': 'ordentliche'},
]

EINGABEWERTE = {
    'versammlung_datum': '2025-12-18',
    'versammlung_uhrzeit': '16:00',
    'versammlung_ort': 'Achat Hotel Offenbach, Ernst-Griesheimer-Platz 7 in 63071 Offenbach',
    'tagesordnung': [
        'Beschlussfassung über die Jahresabrechnung 2024',
        'Beschlussfassung über den Wirtschaftsplan 2026',
        'Beschlussfassung über die Bestellung des Verwalters',
        'Beschlussfassung über die Verlegung eines Leerrohres zur späteren Elektrifizierung der Stellplätze',
    ],
    'art': 'ordentliche',
}

_VOLLMACHT = (
    '<p>Hiermit bevollmächtige ich</p>'
    '<p>{{ empfaenger.anschrift_zeilen }}</p>'
    '<p>&#9744; Herrn/Frau _______________________________<br>oder<br>'
    '&#9744; die Verwalterin, Demme Immobilien Verwaltung GmbH</p>'
    '<p>mich in anstehenden Eigentümerversammlungen, an denen ich nicht teilnehmen kann, '
    'zu vertreten und mein Stimmrecht auszuüben. Soweit ich zu den Tagesordnungspunkten keine '
    'gesonderte Weisung zur Ausübung des Stimmrechts erteile, soll mein Vertreter nach eigenem '
    'Ermessen mein Stimmrecht ausüben.</p>'
    '<p style="margin-top: 22mm">_______________________ '
    '<span style="display:inline-block; width: 12mm"></span>__________________________<br>'
    'Ort, Datum <span style="display:inline-block; width: 46mm"></span>Unterschrift</p>'
    '<p style="margin-top: 14mm">{{ schreiben.unser_zeichen }}</p>'
)

ETV_INHALT = [
    {'typ': 'text', 'inhalt': (
        'wir berufen für\n\n'
        '<strong>{{ eingabe.versammlung_datum | datum_lang }} um {{ eingabe.versammlung_uhrzeit | uhrzeit }}</strong>\n\n'
        'eine {{ eingabe.art }} Eigentümerversammlung ein. Die Versammlung findet im '
        '{{ eingabe.versammlung_ort }} statt.\n\nTagesordnung:'
    )},
    {'typ': 'liste', 'quelle': 'eingabe.tagesordnung', 'nummeriert': True},
    {'typ': 'text', 'inhalt': (
        '<p><strong>Die Tagesordnung können Sie im Serviceportal www.casavi.de abrufen. Sofern die '
        'Einladungsunterlagen Entwürfe von Beschlusstexten enthalten, handelt es sich hierbei '
        'ausdrücklich um Vorschläge zu einer möglichen Beschlussfassung. Den Wohnungseigentümern '
        'steht es im Rahmen der Eigentümerversammlung frei, diese Beschlussvorlage zu übernehmen, '
        'zu ändern oder gänzlich zu verwerfen.</strong></p>'
    )},
    {'typ': 'text', 'inhalt': 'Für Rückfragen stehen wir Ihnen gerne zur Verfügung.'},
    {'typ': 'anlage_seite', 'titel': 'Vertretungsvollmacht', 'inhalt': _VOLLMACHT},
]


def etv_version(speichern=False) -> VorlagenVersion:
    """Vorlage A.1 ``etv_einladung`` (Inhalt nach Spec Anhang A.1) - standardmäßig ungespeichert."""
    vorlage = Vorlage(code='etv_einladung', bezeichnung='Einladung Eigentümerversammlung',
                      anlass='etv_einladung')
    version = VorlagenVersion(
        vorlage=vorlage, version=1, betreff='Einberufung der Eigentümerversammlung',
        inhalt=ETV_INHALT, eingabefelder=EINGABEFELDER, status='freigegeben',
    )
    if speichern:
        vorlage.save()
        version.vorlage = vorlage
        version.save()
    return version


def _logo_dokument(dateiname: str, kategorie: str, user) -> Dokument:
    return Dokument.objects.create(
        datei=ContentFile((ASSETS / dateiname).read_bytes(), name=dateiname),
        dateiname=dateiname, kategorie=kategorie, hochgeladen_von=user,
        dokument_typ='sonstiges',
    )


def demme_briefbogen(user, **abweichungen) -> Briefbogen:
    """Standard-Briefbogen mit den Demme-Daten aus Spec 5.3/5.4 und den extrahierten Logos."""
    werte = dict(
        bezeichnung='Demme — Standard',
        firma_name='Demme Immobilien Verwaltung GmbH',
        firma_strasse='Coventrystraße 32', firma_plz='65934', firma_ort='Frankfurt am Main',
        telefon='069-96 75 20 90', email='info@demme-immobilien.de',
        sprechzeiten='MO, MI, FR\tvon 08.00-11.30 Uhr\nDI, DO\tvon 13.30-17.00 Uhr',
        hinweis_infoblock='Bürotermine nur nach vorheriger telefonischer Absprache',
        logo=_logo_dokument('demme_logo.jpeg', 'Briefbogen', user),
        fuss_logo=_logo_dokument('verbandslogo.png', 'Briefbogen', user),
        fuss_firma_zeile1='Geschäftsführer: Patrik Maurer · HRB 7182 AG Königstein im Taunus',
        fuss_firma_zeile2='Frankfurter Volksbank · IBAN: DE02 5019 0000 6300 2110 10 · BIC FFVBDEFFXXX',
        fuss_firma_zeile3='Frankfurt - Königstein/Taunus - Erfurt',
        pflichtangaben=('Demme Immobilien Verwaltung GmbH · Sitz Frankfurt am Main · '
                        'Amtsgericht Königstein im Taunus HRB 7182 · Geschäftsführer: Patrik Maurer'),
        pflichtangaben_anzeigen=True,
        steuerzeichen_unsichtbar='Porto!Demme',
        ist_standard=True,
    )
    werte.update(abweichungen)
    return Briefbogen.objects.create(**werte)


def anhang_b_kontext(szenario, briefbogen, unterzeichner, heute=date(2026, 9, 29)) -> dict:
    """Kontext des Layout-Tests (Anhang B) auf Basis von ``fixtures.szenario``.

    Das Szenario liefert Eheleute Dr. Max und Erika Mustermann, WEG Musterstraße 1,
    Fläche 0012 und ein Zahlungsverkehrskonto; Objektnummer, IBAN, BIC und Bankname
    werden auf die Werte aus Anhang B gesetzt (Kontext-Werte, keine DB-Änderung).
    """
    kontext = kontext_service.baue_kontext(
        'etv_einladung', person=szenario.person, objekt=szenario.objekt, einheit=szenario.einheit,
        eigentumsverhaeltnis=szenario.ev, briefbogen=briefbogen, unterzeichner=unterzeichner,
        schreiben_nummer='KS-2026-000001', heute=heute,
    )
    kontext['objekt']['objektnummer'] = '53'
    kontext['schreiben']['unser_zeichen'] = '53/100123'
    kontext['bank'].update(iban=ANHANG_B_IBAN, bic=ANHANG_B_BIC, bankname='Testbank')
    return kontext
