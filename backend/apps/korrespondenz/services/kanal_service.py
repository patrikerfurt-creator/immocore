"""Kanal-Auflösung eines Schreibens (Spec 7.3).

Kanal = Wunsch (explizit, sonst ``Vorlage.kanal_standard``) x ``Person.zustellweg``.

* E-Mail nur, wenn der Wunsch E-Mail zulässt (``email`` oder ``beides``) UND
  die Person ``zustellweg='email'`` gewählt, der Zustellung zugestimmt
  (``zustellweg_zustimmung_am``) und eine E-Mail-Adresse hinterlegt hat.
  Sonst Brief.
* "Auch Brief": bei ``beides`` und bei der LETZTEN Mahnstufe des Objekts
  (``MahnEinstellung.anzahl_mahnstufen``, ohne Konfiguration: Stufe 3) geht ein E-Mail-Schreiben
  ZUSÄTZLICH als Brief raus. Für einen reinen Brief-Kanal ist das ohnehin erfüllt.

Reine Funktionen, kein Statuswechsel, keine Datenbankschreibzugriffe.
"""
from dataclasses import dataclass

STUFE_3_ANLASS = 'mahnung_stufe_3'      # Vorlage der letzten Mahnstufe (mahn_anbindung_service)
STUFE_3 = 3                              # Fallback der letzten Stufe, wenn keine MahnEinstellung existiert


@dataclass(frozen=True)
class KanalEntscheidung:
    """Ergebnis der Kanal-Auflösung.

    ``kanal``: Hauptkanal (``brief``/``email``). ``auch_brief``: zusätzlich ein
    Brief (nur bei ``kanal='email'`` relevant). ``hinweis``: Grund, wenn der
    Wunsch nicht erfüllt werden konnte (leer = Wunsch erfüllt).
    """
    kanal: str
    auch_brief: bool = False
    hinweis: str = ''


def erste_email(person) -> str:
    """Erste brauchbare E-Mail-Adresse einer Person (``emails``-Liste, sonst Legacy-Feld ``email``).

    Einträge der Liste können Strings oder Dicts (``adresse``/``email``/``wert``) sein.
    """
    for eintrag in (person.emails or []):
        if isinstance(eintrag, str) and eintrag.strip():
            return eintrag.strip()
        if isinstance(eintrag, dict):
            for schluessel in ('adresse', 'email', 'wert'):
                wert = (eintrag.get(schluessel) or '').strip()
                if wert:
                    return wert
    return (person.email or '').strip()


def email_zustellung_moeglich(person) -> tuple:
    """``(ok, grund)``: Zustellweg E-Mail gewählt, Zustimmung erteilt, Adresse vorhanden."""
    if person.zustellweg != 'email':
        return False, 'Zustellweg der Person ist nicht E-Mail.'
    if not person.zustellweg_zustimmung_am:
        return False, 'Keine Zustimmung zur E-Mail-Zustellung hinterlegt.'
    if not erste_email(person):
        return False, 'Keine E-Mail-Adresse hinterlegt.'
    return True, ''


def letzte_stufe_von(mahnung) -> int | None:
    """Letzte Mahnstufe des Objekts der Mahnung (``MahnEinstellung.anzahl_mahnstufen``).

    ``None``, wenn keine Mahnung/keine Konfiguration vorliegt (dann gilt ``STUFE_3``).
    """
    try:
        return mahnung.personenkonto.objekt.mahn_einstellung.anzahl_mahnstufen
    except AttributeError:      # auch RelatedObjectDoesNotExist (ohne MahnEinstellung)
        return None


def ist_letzte_mahnstufe(anlass: str, mahnstufe, letzte_stufe=None) -> bool:
    """Letzte Mahnstufe über den Anlass der Vorlage oder die Stufe der verknüpften Mahnung."""
    return anlass == STUFE_3_ANLASS or (mahnstufe or 0) >= (letzte_stufe or STUFE_3)


ist_mahnstufe_3 = ist_letzte_mahnstufe      # alter Name


def kanal_aufloesen(vorlage, person, *, kanal=None, mahnstufe=None, letzte_stufe=None) -> KanalEntscheidung:
    """Löst den Kanal für ``person`` auf (siehe Modul-Docstring).

    ``kanal``: expliziter Wunsch (``brief``/``email``/``beides``), sonst
    ``vorlage.kanal_standard``. ``mahnstufe``: ``Mahnung.mahnstufe`` des
    verknüpften Schreibens (oder ``None``). ``letzte_stufe``: letzte Mahnstufe
    des Objekts (``letzte_stufe_von``), ``None`` = Fallback ``STUFE_3``.
    """
    wunsch = kanal or vorlage.kanal_standard
    if wunsch not in ('brief', 'email', 'beides'):
        raise ValueError(f'Unbekannter Kanal: {wunsch!r}')
    if wunsch == 'brief':
        return KanalEntscheidung('brief')

    ok, grund = email_zustellung_moeglich(person)
    if not ok:
        return KanalEntscheidung('brief', hinweis=f'Versand als Brief: {grund}')

    auch_brief = wunsch == 'beides' or ist_letzte_mahnstufe(vorlage.anlass, mahnstufe, letzte_stufe)
    return KanalEntscheidung('email', auch_brief=auch_brief)


def auch_brief(schreiben) -> bool:
    """Geht zu diesem (E-Mail-)Schreiben zusätzlich ein Brief raus?"""
    vorlage = schreiben.vorlage_version.vorlage
    mahnstufe = schreiben.mahnung.mahnstufe if schreiben.mahnung_id else None
    return vorlage.kanal_standard == 'beides' or ist_letzte_mahnstufe(
        vorlage.anlass, mahnstufe, letzte_stufe_von(schreiben.mahnung) if schreiben.mahnung_id else None,
    )


def braucht_brief(schreiben) -> bool:
    """Muss dieses Schreiben (auch) gedruckt werden?"""
    return schreiben.kanal == 'brief' or auch_brief(schreiben)
