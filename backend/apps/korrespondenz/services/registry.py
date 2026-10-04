"""Platzhalter-Registry (Spec 4.2) — Metadaten-Teil.

Eine Quelle für Editor, Vorschau, Validierung und generierte Doku. Dieses
Modul enthält NUR Metadaten (keine Modelle, keine DB-Zugriffe). Die Funktion,
die aus echten Referenzen das Kontext-Dict baut, steht in
``kontext_service.baue_kontext`` und liefert je Anlass ausschließlich Werte
aus den hier dokumentierten Platzhaltern (Test 6).

Namensschema: ``<gruppe>.<name>`` (z. B. ``empfaenger.anschrift_zeilen``), im
Vorlagentext ``{{ empfaenger.anschrift_zeilen }}``. Ausnahme: die Gruppe
``eingabe`` ist dynamisch (laut ``eingabefelder`` der Version) und kommt nur
über ``metadaten(anlass, eingabefelder=...)`` dazu.

Typen: ``text``, ``zahl``, ``betrag``, ``datum``, ``bool``, ``liste``, ``tabelle``.
"""

ANLAESSE = (
    'eigentuemer_begruessung',
    'eigentuemer_verabschiedung',
    'mahnung_stufe_1',
    'mahnung_stufe_2',
    'mahnung_stufe_3',
    'etv_einladung',
    'eigentuemer_allgemein',
    'vorgang_antwort',
)

_ALLE = ('empfaenger', 'objekt', 'einheit', 'schreiben', 'verwaltung', 'bank')

# Welche Gruppen (Tabelle 4.2, Spalte "Anlässe") je Anlass gelten.
GRUPPEN_JE_ANLASS = {
    'eigentuemer_begruessung':    _ALLE + ('ev', 'hausgeld', 'wechsel', 'eingabe'),
    'eigentuemer_verabschiedung': _ALLE + ('ev', 'wechsel', 'eingabe'),
    'mahnung_stufe_1':            _ALLE + ('ev', 'mahnung', 'eingabe'),
    'mahnung_stufe_2':            _ALLE + ('ev', 'mahnung', 'eingabe'),
    'mahnung_stufe_3':            _ALLE + ('ev', 'mahnung', 'eingabe'),
    'etv_einladung':              _ALLE + ('ev', 'versammlung', 'eingabe'),
    'eigentuemer_allgemein':      _ALLE + ('ev', 'eingabe'),
    'vorgang_antwort':            _ALLE + ('vorgang', 'eingabe'),
}


def _p(gruppe, name, beschreibung, typ, beispiel):
    return {
        'gruppe': gruppe, 'name': f'{gruppe}.{name}',
        'beschreibung': beschreibung, 'typ': typ, 'beispiel': beispiel,
    }


PLATZHALTER = (
    # --- empfaenger ---------------------------------------------------
    _p('empfaenger', 'anschrift_zeilen', 'Anschriftfeld, höchstens 7 Zeilen', 'liste',
       ['Eheleute', 'Dr. Max Mustermann', 'Erika Mustermann', 'Musterweg 5', '60311 Frankfurt am Main']),
    _p('empfaenger', 'briefanrede', 'Briefanrede (1. Person)', 'text', 'Sehr geehrte Frau Mustermann,'),
    _p('empfaenger', 'briefanrede2', 'Briefanrede 2. Person (leer bei Einzelperson)', 'text',
       'sehr geehrter Herr Mustermann,'),
    _p('empfaenger', 'name', 'Name des Empfängers', 'text', 'Dr. Max und Erika Mustermann'),
    _p('empfaenger', 'personennummer', 'Personennummer', 'text', '100123'),
    # --- objekt -------------------------------------------------------
    _p('objekt', 'objektnummer', 'Objektnummer', 'text', '53'),
    _p('objekt', 'bezeichnung', 'Bezeichnung des Objekts', 'text', 'WEG Musterstraße 1'),
    _p('objekt', 'anschrift', 'Anschrift des Objekts', 'text', 'Musterstraße 1, 60311 Frankfurt am Main'),
    _p('objekt', 'ist_weg', 'Objekt ist eine WEG', 'bool', True),
    # --- einheit ------------------------------------------------------
    _p('einheit', 'einheit_nr', 'Einheitennummer', 'text', '12'),
    _p('einheit', 'flaechennummer', 'Flächennummer', 'text', '0012'),
    _p('einheit', 'lage', 'Lage der Einheit', 'text', 'Wohnung 2. OG links'),
    _p('einheit', 'typ', 'Einheitentyp', 'text', 'Wohnung'),
    # --- schreiben ----------------------------------------------------
    _p('schreiben', 'unser_zeichen', 'Unser Zeichen: Objektnummer/Personenkontonummer', 'text', '53/0012'),
    _p('schreiben', 'ihr_zeichen', 'Ihr Zeichen (optional, kann leer sein)', 'text', ''),
    _p('schreiben', 'ihr_schreiben_vom', 'Ihr Schreiben vom (optional)', 'datum', '2026-09-01'),
    _p('schreiben', 'datum', 'Schreibensdatum', 'datum', '2026-09-29'),
    _p('schreiben', 'nummer', 'Schreibennummer', 'text', 'KS-2026-000123'),
    # --- verwaltung ---------------------------------------------------
    _p('verwaltung', 'firma', 'Name der Verwaltungsfirma (Briefbogen)', 'text',
       'Demme Immobilien Verwaltung GmbH'),
    _p('verwaltung', 'unterzeichner_vorname', 'Vorname des Unterzeichners', 'text', 'Patrik'),
    _p('verwaltung', 'unterzeichner_nachname', 'Nachname des Unterzeichners', 'text', 'Maurer'),
    _p('verwaltung', 'betreuer_name', 'Name des Objektbetreuers', 'text', 'Anna Beispiel'),
    _p('verwaltung', 'betreuer_telefon', 'Telefon des Objektbetreuers', 'text', '069-96 75 20 90'),
    _p('verwaltung', 'betreuer_email', 'E-Mail des Objektbetreuers', 'text', 'a.beispiel@demme-immobilien.de'),
    # --- bank (WEG-Objekte, Spec 5.4) ---------------------------------
    _p('bank', 'weg_name', 'Name der WEG (Objektbezeichnung)', 'text', 'WEG Musterstraße 1'),
    _p('bank', 'iban', 'IBAN des Zahlungsverkehrskontos', 'text', 'DE00 0000 0000 0000 0000 00'),
    _p('bank', 'bic', 'BIC des Zahlungsverkehrskontos', 'text', 'TESTDEFFXXX'),
    _p('bank', 'bankname', 'Name der Bank (aus der IBAN abgeleitet, schwifty)', 'text', 'Testbank'),
    _p('bank', 'kontoinhaber', 'Kontoinhaber', 'text', 'WEG Musterstraße 1'),
    _p('bank', 'glaeubiger_id', 'Gläubiger-ID des Objekts', 'text', 'DE98ZZZ09999999999'),
    # --- ev -----------------------------------------------------------
    _p('ev', 'beginn', 'Beginn des Eigentumsverhältnisses', 'datum', '2026-09-01'),
    _p('ev', 'sepa_mandat_vorhanden', 'Aktives SEPA-Mandat liegt vor', 'bool', False),
    _p('ev', 'sepa_mandat_fehlt', 'Kein aktives SEPA-Mandat', 'bool', True),
    # --- versammlung (nur Anlass etv_einladung; liest aus der Eigentümerversammlung, Spec 9.4) ---
    _p('versammlung', 'termin', 'Termin der Versammlung (Datum und Uhrzeit, Ortszeit; Filter datum_lang / uhrzeit)',
       'datum', '2026-12-18T16:00:00'),
    _p('versammlung', 'ort', 'Versammlungsort', 'text',
       'Achat Hotel Offenbach, Ernst-Griesheimer-Platz 7 in 63071 Offenbach'),
    _p('versammlung', 'tagesordnung', 'Titel der Tagesordnungspunkte in Reihenfolge', 'liste',
       ['Beschlussfassung über die Jahresabrechnung 2025', 'Beschlussfassung über den Wirtschaftsplan 2027']),
    _p('versammlung', 'art', 'Art der Versammlung als Adjektiv („eine … Eigentümerversammlung“)', 'text',
       'ordentliche'),
    # --- hausgeld -----------------------------------------------------
    _p('hausgeld', 'monatsbetrag', 'Monatliches Hausgeld gesamt', 'betrag', '350.00'),
    _p('hausgeld', 'gueltig_ab', 'Hausgeld gültig ab', 'datum', '2026-09-01'),
    _p('hausgeld', 'positionen', 'Tabelle der Hausgeld-Positionen', 'tabelle',
       [{'bezeichnung': 'Hausgeld', 'betrag': '300.00'}, {'bezeichnung': 'Rücklage', 'betrag': '50.00'}]),
    # --- wechsel ------------------------------------------------------
    _p('wechsel', 'wechsel_datum', 'Datum des Eigentümerwechsels', 'datum', '2026-09-01'),
    _p('wechsel', 'voreigentuemer_name', 'Name des Voreigentümers', 'text', 'Hans Alt'),
    # --- mahnung ------------------------------------------------------
    _p('mahnung', 'stufe', 'Mahnstufe (Wert von Mahnung.mahnstufe)', 'zahl', 1),
    _p('mahnung', 'offene_posten', 'Tabelle der offenen Posten', 'tabelle',
       [{'faellig_ab': '2026-08-01', 'bezeichnung': 'Hausgeld 08/2026',
         'betrag_ursprung': '350.00', 'betrag_offen': '350.00'}]),
    _p('mahnung', 'summe_hauptforderung', 'Summe der offenen Hauptforderung', 'betrag', '350.00'),
    _p('mahnung', 'gebuehr', 'Mahngebühr', 'betrag', '5.00'),
    _p('mahnung', 'zinsen', 'Verzugszinsen', 'betrag', '1.20'),
    _p('mahnung', 'gesamtbetrag', 'Hauptforderung + Gebühr + Zinsen', 'betrag', '356.20'),
    _p('mahnung', 'frist', 'Zahlungsfrist (Mahnlauf-Datum + Frist der Stufe, nächster Werktag)', 'datum', '2026-10-13'),
    _p('mahnung', 'zinssatz', 'Verzugszinssatz (Basiszinssatz + 5 Prozentpunkte)', 'text', '8,62 %'),
    _p('mahnung', 'basiszinssatz', 'Basiszinssatz', 'text', '3,62 %'),
    # --- vorgang ------------------------------------------------------
    _p('vorgang', 'nummer', 'Vorgangsnummer', 'text', 'V-2026-000042'),
    _p('vorgang', 'betreff', 'Betreff des Vorgangs', 'text', 'Schaden im Treppenhaus'),
)

# Standard-Spalten der systemerzeugten Tabellen (Blocktyp ``tabelle``, Spec 3.4).
# ``format``: text | datum | euro.
TABELLEN = {
    'mahnung.offene_posten': [
        {'feld': 'faellig_ab', 'titel': 'Fällig am', 'format': 'datum'},
        {'feld': 'bezeichnung', 'titel': 'Bezeichnung', 'format': 'text'},
        {'feld': 'betrag_ursprung', 'titel': 'Ursprungsbetrag', 'format': 'euro'},
        {'feld': 'betrag_offen', 'titel': 'Offen', 'format': 'euro'},
    ],
    'hausgeld.positionen': [
        {'feld': 'bezeichnung', 'titel': 'Position', 'format': 'text'},
        {'feld': 'betrag', 'titel': 'Monatlich', 'format': 'euro'},
    ],
}


def gruppen_fuer(anlass: str) -> tuple:
    """Gruppen, die für den Anlass gelten. ``KeyError`` bei unbekanntem Anlass."""
    return GRUPPEN_JE_ANLASS[anlass]


def _eingabe_eintrag(feld: dict) -> dict:
    typ_map = {
        'text': 'text', 'mehrzeilig': 'text', 'datum': 'datum', 'uhrzeit': 'text',
        'betrag': 'betrag', 'liste': 'liste', 'ja_nein': 'bool',
    }
    return {
        'gruppe': 'eingabe',
        'name': f"eingabe.{feld['name']}",
        'beschreibung': feld.get('label') or feld['name'],
        'typ': typ_map.get(feld.get('typ'), 'text'),
        'beispiel': None,
    }


def metadaten(anlass: str, eingabefelder=None) -> list:
    """Dokumentierte Platzhalter des Anlasses als ``[{name, beschreibung, typ, beispiel, gruppe}]``.

    ``eingabefelder`` (Definition aus ``VorlagenVersion.eingabefelder``) ergänzt
    die dynamische Gruppe ``eingabe``.
    """
    erlaubt = set(gruppen_fuer(anlass))
    eintraege = [dict(p) for p in PLATZHALTER if p['gruppe'] in erlaubt]
    for feld in eingabefelder or []:
        eintraege.append(_eingabe_eintrag(feld))
    return eintraege


def dokumentierte_namen(anlass: str, eingabefelder=None) -> set:
    """Menge der vollen Platzhalternamen (``gruppe.name``) des Anlasses."""
    return {p['name'] for p in metadaten(anlass, eingabefelder)}
