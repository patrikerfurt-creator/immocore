"""Seed-Daten des Moduls Vorlagen & Korrespondenz (Phase 7, Spec 12.8 / Anhang A).

Reine Daten, keine Logik und keine DB-Zugriffe. Die Texte folgen wörtlich
Spec-Anhang A. ALLE Mustervorlagen sind Entwürfe: juristische Prüfung und
Freigabe stehen aus (``seed_service`` legt sie nur als Status ``entwurf`` an).
"""

LOGO_DATEI = 'demme_logo.jpeg'
LOGO_KATEGORIE = 'Briefbogen'

# Sprechzeiten: Tag und Zeit sind per TAB getrennt (so erwartet es
# brief_layout_service._sprechzeit_zeile; identisch zu den freigegebenen Demo-PDFs).
BRIEFBOGEN = dict(
    bezeichnung='Demme — Standard',
    firma_name='Demme Immobilien Verwaltung GmbH',
    firma_strasse='Coventrystraße 32',
    firma_plz='65934',
    firma_ort='Frankfurt am Main',
    telefon='069-96 75 20 90',
    email='info@demme-immobilien.de',
    web='',
    sprechzeiten='MO, MI, FR\tvon 08.00-11.30 Uhr\nDI, DO\tvon 13.30-17.00 Uhr',
    hinweis_infoblock='Bürotermine nur nach vorheriger telefonischer Absprache',
    fuss_firma_zeile1='Geschäftsführer: Patrik Maurer · HRB 143119 AG Frankfurt am Main',
    fuss_firma_zeile2='Frankfurter Volksbank · IBAN: DE02 5019 0000 6300 2110 10 · BIC FFVBDEFFXXX',
    fuss_firma_zeile3='Frankfurt - Königstein/Taunus - Erfurt',
    pflichtangaben=(
        'Demme Immobilien Verwaltung GmbH · Sitz Frankfurt am Main · '
        'Amtsgericht Frankfurt am Main · HRB 143119 · Geschäftsführer: Patrik Maurer'
    ),
    pflichtangaben_anzeigen=True,
    steuerzeichen_unsichtbar='Porto!Demme',
    ist_standard=True,
    aktiv=True,
)

_RUECKFRAGEN = 'Für Rückfragen stehen wir Ihnen gerne zur Verfügung.'

# --- A.1 etv_einladung -----------------------------------------------------

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

ETV_EINLADUNG = dict(
    code='etv_einladung',
    bezeichnung='Einladung Eigentümerversammlung (Serienbrief)',
    anlass='etv_einladung',
    kanal_standard='brief',
    einzeln_bearbeitbar=False,
    betreff='Einberufung der Eigentümerversammlung',
    eingabefelder=[
        {'name': 'versammlung_datum', 'label': 'Datum der Versammlung', 'typ': 'datum', 'pflicht': True},
        {'name': 'versammlung_uhrzeit', 'label': 'Uhrzeit', 'typ': 'uhrzeit', 'pflicht': True},
        {'name': 'versammlung_ort', 'label': 'Ort / Adresse', 'typ': 'mehrzeilig', 'pflicht': True},
        {'name': 'tagesordnung', 'label': 'Tagesordnungspunkte', 'typ': 'liste', 'pflicht': True},
        {'name': 'art', 'label': 'Art', 'typ': 'text', 'pflicht': False, 'default': 'ordentliche'},
    ],
    inhalt=[
        {'typ': 'text', 'inhalt': (
            'wir berufen für\n\n'
            '<strong>{{ eingabe.versammlung_datum | datum_lang }} um '
            '{{ eingabe.versammlung_uhrzeit | uhrzeit }}</strong>\n\n'
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
        {'typ': 'text', 'inhalt': _RUECKFRAGEN},
        {'typ': 'anlage_seite', 'titel': 'Vertretungsvollmacht', 'inhalt': _VOLLMACHT},
    ],
)

# --- A.2 eigentuemer_begruessung --------------------------------------------

EIGENTUEMER_BEGRUESSUNG = dict(
    code='eigentuemer_begruessung',
    bezeichnung='Begrüßung neuer Eigentümer',
    anlass='eigentuemer_begruessung',
    kanal_standard='beides',
    einzeln_bearbeitbar=True,
    betreff='Willkommen in der Eigentümergemeinschaft',
    email_begleittext=(
        'anbei erhalten Sie unser Begrüßungsschreiben als PDF. '
        'Bei Fragen erreichen Sie uns unter der im Schreiben genannten Telefonnummer.'
    ),
    eingabefelder=[],
    inhalt=[
        {'typ': 'text', 'inhalt': (
            'wir freuen uns, Sie als neues Mitglied der Gemeinschaft der Wohnungseigentümer '
            '{{ objekt.bezeichnung }} begrüßen zu dürfen. Als Verwaltung sind wir ab dem '
            '{{ wechsel.wechsel_datum | datum }} Ihr Ansprechpartner für alle Fragen rund um das '
            'gemeinschaftliche Eigentum.\n\n'
            'Ihr monatliches Hausgeld beträgt ab dem {{ hausgeld.gueltig_ab | datum }} '
            '{{ hausgeld.monatsbetrag | euro }} und ist jeweils zum Monatsbeginn fällig.'
        )},
        {'typ': 'bedingt', 'bedingung': 'ev.sepa_mandat_fehlt', 'inhalt': (
            'Damit wir das Hausgeld bequem per Lastschrift einziehen können, senden Sie uns bitte '
            'das beigefügte SEPA-Lastschriftmandat unterschrieben zurück. Bis dahin überweisen Sie '
            'bitte auf das Konto der Gemeinschaft (IBAN {{ bank.iban | iban }}).'
        )},
        {'typ': 'text', 'inhalt': (
            'Ihr persönlicher Ansprechpartner ist {{ verwaltung.betreuer_name }}, erreichbar unter '
            '{{ verwaltung.betreuer_telefon }} oder {{ verwaltung.betreuer_email }}. '
            'Wir freuen uns auf eine gute Zusammenarbeit.'
        )},
    ],
    # Anlagen: das SEPA-Formular (dokument) hängt Patrik vor der Aktivierung an.
    anlagen=[
        dict(art='dokument', bezeichnung='SEPA-Lastschriftmandat', pflicht=True, reihenfolge=1,
             bedingung='ev.sepa_mandat_fehlt', objekt_kategorie=''),
        dict(art='objekt_kategorie', bezeichnung='Hausordnung', pflicht=False, reihenfolge=2,
             bedingung='', objekt_kategorie='Hausordnung'),
    ],
)

# --- A.4 / A.5 Mahnungen -----------------------------------------------------

_MAHN_EINLEITUNG = (
    # Option A: bewusst OHNE „trotz unserer Zahlungserinnerung" (keine Stufe 1 als Voraussetzung).
    'bis heute konnten wir keinen Zahlungseingang für die folgenden Beträge feststellen:'
)
_MAHN_SUMMEN = (
    'Hauptforderung {{ mahnung.summe_hauptforderung | euro }} · Mahngebühr {{ mahnung.gebuehr | euro }} · '
    'Verzugszinsen {{ mahnung.zinsen | euro }} · <strong>Gesamt {{ mahnung.gesamtbetrag | euro }}</strong>, '
    'zahlbar bis {{ mahnung.frist | datum }}.'
)
_MAHN_GEBUEHR = 'Die Mahngebühr beruht auf dem Beschluss der Eigentümergemeinschaft.'
_MAHN_ZINSEN = (
    'Verzugszinsen berechnen wir in Höhe von 5 Prozentpunkten über dem Basiszinssatz '
    '(derzeit {{ mahnung.zinssatz }}). Sollten Sie sich in Zahlungsschwierigkeiten befinden, '
    'sprechen Sie uns bitte an.'
)
_MAHN_KLAGE = (
    'Sollte der Betrag bis zum {{ mahnung.frist | datum }} nicht auf dem Konto der Gemeinschaft '
    'eingegangen sein, werden wir die Forderung im Namen der Gemeinschaft der Wohnungseigentümer '
    'ohne weitere Ankündigung gerichtlich geltend machen. Die dadurch entstehenden Kosten gehen '
    'zu Ihren Lasten.'
)


def _mahn_inhalt(mit_klage: bool) -> list:
    bloecke = [
        {'typ': 'text', 'inhalt': _MAHN_EINLEITUNG},
        {'typ': 'tabelle', 'quelle': 'mahnung.offene_posten'},
        {'typ': 'text', 'inhalt': _MAHN_SUMMEN},
        {'typ': 'bedingt', 'bedingung': 'mahnung.gebuehr > 0', 'inhalt': _MAHN_GEBUEHR},
        {'typ': 'text', 'inhalt': _MAHN_ZINSEN},
    ]
    if mit_klage:
        bloecke.append({'typ': 'text', 'inhalt': _MAHN_KLAGE})
    return bloecke


# ``parameter`` bewusst leer: die Zahlungsfrist kommt aus der globalen Mahnstaffel
# (mahnwesen.zahlungsfrist_tage); ``frist_tage`` wäre nur ein Fallback für Altbestand.
MAHNUNG_STUFE_2 = dict(
    code='mahnung_stufe_2',
    bezeichnung='1. Mahnung',
    anlass='mahnung_stufe_2',
    kanal_standard='brief',
    einzeln_bearbeitbar=False,
    betreff='Mahnung Hausgeld',
    eingabefelder=[],
    pflicht_platzhalter=['mahnung.gesamtbetrag', 'mahnung.frist'],
    parameter={},
    inhalt=_mahn_inhalt(mit_klage=False),
)

MAHNUNG_STUFE_3 = dict(
    code='mahnung_stufe_3',
    bezeichnung='Letzte Mahnung',
    anlass='mahnung_stufe_3',
    kanal_standard='brief',
    einzeln_bearbeitbar=False,
    betreff='Letzte Mahnung Hausgeld',
    eingabefelder=[],
    pflicht_platzhalter=['mahnung.gesamtbetrag', 'mahnung.frist'],
    parameter={},
    inhalt=_mahn_inhalt(mit_klage=True),
)

# --- A.6 eigentuemer_allgemein ----------------------------------------------

EIGENTUEMER_ALLGEMEIN = dict(
    code='eigentuemer_allgemein',
    bezeichnung='Allgemeines Eigentümerschreiben (Serienbrief)',
    anlass='eigentuemer_allgemein',
    kanal_standard='brief',
    einzeln_bearbeitbar=True,
    betreff='{{ eingabe.betreff }}',
    eingabefelder=[
        {'name': 'betreff', 'label': 'Betreff', 'typ': 'text', 'pflicht': True},
        {'name': 'inhalt', 'label': 'Inhalt', 'typ': 'mehrzeilig', 'pflicht': True},
    ],
    inhalt=[
        # white-space: pre-line übernimmt die Zeilenumbrüche aus dem mehrzeiligen Eingabefeld.
        {'typ': 'text', 'inhalt': '<p style="white-space: pre-line">{{ eingabe.inhalt }}</p>'},
        {'typ': 'text', 'inhalt': _RUECKFRAGEN},
    ],
)

# --- eigentuemer_verabschiedung (kein Volltext in Anhang A: sachlicher Entwurf) ---

EIGENTUEMER_VERABSCHIEDUNG = dict(
    code='eigentuemer_verabschiedung',
    bezeichnung='Verabschiedung Voreigentümer',
    anlass='eigentuemer_verabschiedung',
    kanal_standard='brief',
    einzeln_bearbeitbar=True,
    betreff='Beendigung Ihrer Mitgliedschaft in der Eigentümergemeinschaft',
    eingabefelder=[],
    inhalt=[
        {'typ': 'text', 'inhalt': (
            'wir bestätigen, dass das Eigentum an Ihrer Einheit in der Gemeinschaft der '
            'Wohnungseigentümer {{ objekt.bezeichnung }} mit Wirkung zum '
            '{{ wechsel.wechsel_datum | datum }} auf den neuen Eigentümer übergegangen ist. '
            'Ab diesem Zeitpunkt sind wir nicht mehr Ihr Ansprechpartner für die Belange der '
            'Gemeinschaft.\n\n'
            'Forderungen und Verpflichtungen aus der Zeit Ihres Eigentums bleiben von diesem '
            'Schreiben unberührt.\n\n'
            'Wir bedanken uns für die Zusammenarbeit und wünschen Ihnen für die Zukunft alles Gute.'
        )},
    ],
)

# Reihenfolge = Anlage-Reihenfolge im Seed.
VORLAGEN = (
    EIGENTUEMER_BEGRUESSUNG,
    EIGENTUEMER_VERABSCHIEDUNG,
    MAHNUNG_STUFE_2,
    MAHNUNG_STUFE_3,
    ETV_EINLADUNG,
    EIGENTUEMER_ALLGEMEIN,
)
