"""
Kreditor-Abgleich und Dubletten-Erkennung (gemeinsame Grundlage).

Bis hierher gab es drei Fassungen derselben Suche: der automatische
Import (``verarbeitung.finde_oder_erstelle_kreditor``), die
Erkennungs-Pipeline (``recognition.erkenne_kreditor``) und die manuelle
Kreditorensuche in ``views``. Nur die letzten beiden kannten
Ähnlichkeitssuche — ausgerechnet der Pfad, der ungefragt neue Kreditoren
anlegt, verglich ausschließlich exakt. Diese Datei ist jetzt die eine
Quelle für alle drei.

Kernbegriffe:

``ergebnis.sicher``     ein eindeutiger Treffer, ohne Rückfrage verwendbar
``ergebnis.verdacht``   etwas stimmt nicht — ein Mensch muss entscheiden
``ergebnis.neu``        nichts Ähnliches gefunden, Neuanlage ist korrekt
"""
from dataclasses import dataclass, field

from django.conf import settings

from ..models import Kreditor, KreditorBankverbindung
from ..normalisierung import normalisiere_iban, normalisiere_kreditorname

# Ab diesem Ähnlichkeitswert gilt ein Name als verdächtig ähnlich und die
# Rechnung wird angehalten. 0.75 ist bewusst eher niedrig: ein Fehlalarm
# kostet einen Klick, eine übersehene Doppelung kostet eine Bereinigung
# quer durch Belege, offene Posten und Konten.
DUBLETTEN_SCHWELLE = getattr(settings, 'KREDITOR_DUBLETTEN_SCHWELLE', 0.75)

# Ab hier gilt ein Name als praktisch identisch — bei abweichender IBAN
# ist das kein "vielleicht dieselbe Firma", sondern ein bekannter
# Lieferant mit neuer Bankverbindung.
NAME_IDENTISCH_SCHWELLE = 0.95

ANLASS_FUZZY_NAME = 'fuzzy_name'
ANLASS_IBAN_ABWEICHUNG = 'iban_abweichung'
ANLASS_NAME_ABWEICHUNG = 'name_abweichung'


@dataclass
class Kandidat:
    kreditor: Kreditor
    score: float
    match_typ: str          # 'iban' | 'iban_zweitkonto' | 'name_exakt' | 'fuzzy'

    def as_dict(self) -> dict:
        return {
            'id': str(self.kreditor.id),
            'name': self.kreditor.name,
            'kreditorennummer': self.kreditor.kreditorennummer or '',
            'iban': self.kreditor.iban or '',
            'aktiv': self.kreditor.aktiv,
            'score': round(self.score, 3),
            'match_typ': self.match_typ,
        }


@dataclass
class AbgleichErgebnis:
    """Ergebnis des Abgleichs. Genau eines von sicher/verdacht/neu trifft zu."""

    kreditor: Kreditor | None = None      # bei 'sicher' gesetzt
    kandidaten: list[Kandidat] = field(default_factory=list)
    anlass: str = ''

    @property
    def sicher(self) -> bool:
        return self.kreditor is not None

    @property
    def verdacht(self) -> bool:
        return self.kreditor is None and bool(self.kandidaten)

    @property
    def neu(self) -> bool:
        return self.kreditor is None and not self.kandidaten


def aehnlichkeit(a: str, b: str) -> float:
    """Ähnlichkeit zweier Firmennamen zwischen 0 und 1.

    Verglichen werden die NORMALISIERTEN Namen. Ohne diesen Schritt teilen
    sich "Meier GmbH" und "Schmidt GmbH" die Bigramme von "gmbh" und
    landen bei einem Wert, der nichts über die Firmen aussagt.
    """
    from ..recognition import _fuzzy_score
    return _fuzzy_score(normalisiere_kreditorname(a), normalisiere_kreditorname(b))


def _kreditor_zu_iban(iban: str) -> tuple[Kreditor | None, str]:
    """Sucht die IBAN in beiden Quellen: Haupt-IBAN und Zweitkonten.

    Deaktivierte Kreditoren werden bewusst MITGESUCHT: ein deaktivierter
    Kreditor ist ein starkes Dubletten-Signal (jemand hat ihn stillgelegt,
    vermutlich weil er doppelt war). Würde er übergangen, legte der Import
    ihn beim nächsten Beleg schlicht neu an.
    """
    if not iban:
        return None, ''

    k = Kreditor.objects.filter(iban=iban).first()
    if k:
        return k, 'iban'

    bv = (
        KreditorBankverbindung.objects
        .select_related('kreditor')
        .filter(iban=iban, aktiv=True)
        .first()
    )
    if bv:
        return bv.kreditor, 'iban_zweitkonto'
    return None, ''


def finde_kandidaten(name: str, iban: str = '', schwelle: float | None = None) -> list[Kandidat]:
    """Alle plausiblen Kreditoren zu Name und IBAN, bester Treffer zuerst."""
    schwelle = DUBLETTEN_SCHWELLE if schwelle is None else schwelle
    iban = normalisiere_iban(iban)
    name_norm = normalisiere_kreditorname(name)

    kandidaten: list[Kandidat] = []
    gesehen: set = set()

    treffer, typ = _kreditor_zu_iban(iban)
    if treffer:
        kandidaten.append(Kandidat(treffer, 1.0, typ))
        gesehen.add(treffer.pk)

    if name_norm:
        for k in Kreditor.objects.filter(name_normalisiert=name_norm).exclude(pk__in=gesehen):
            kandidaten.append(Kandidat(k, 0.92, 'name_exakt'))
            gesehen.add(k.pk)

    if name:
        # Der Fuzzy-Durchlauf geht über alle Kreditoren — bei der zu
        # erwartenden Größenordnung (einige hundert) unkritisch und
        # deutlich einfacher als ein Trigram-Index.
        for k in Kreditor.objects.exclude(pk__in=gesehen):
            score = aehnlichkeit(name, k.name)
            if score >= schwelle:
                kandidaten.append(Kandidat(k, min(score, 0.90), 'fuzzy'))

    kandidaten.sort(key=lambda k: k.score, reverse=True)
    return kandidaten


def gleiche_iban(kreditor: Kreditor, iban: str) -> bool:
    """Kennt der Kreditor diese IBAN — als Haupt- oder Zweitkonto?"""
    if not iban:
        return False
    if normalisiere_iban(kreditor.iban or '') == iban:
        return True
    return kreditor.bankverbindungen.filter(iban=iban, aktiv=True).exists()


def gleiche_kreditoren(name: str, iban: str = '') -> AbgleichErgebnis:
    """Entscheidet, ob ein Beleg einem bestehenden Kreditor gehört.

    Drei Ausgänge (siehe Modul-Docstring). Die Verdachtsfälle sind
    bewusst breiter als reine Namensähnlichkeit:

    * Fuzzy-Namenstreffer ohne exakte Bestätigung
    * bekannter Name, ABER abweichende Bankverbindung — der klassische
      Rechnungsbetrug; hier ist eine menschliche Prüfung wichtiger als
      bei jeder Namensähnlichkeit
    * bekannte Bankverbindung, ABER deutlich abweichender Name
    * Treffer auf einem DEAKTIVIERTEN Kreditor
    """
    iban = normalisiere_iban(iban)
    kandidaten = finde_kandidaten(name, iban)

    if not kandidaten:
        return AbgleichErgebnis()

    bester = kandidaten[0]

    # Ein deaktivierter Kreditor wird nie stillschweigend weiterverwendet
    # und auch nicht ignoriert — beides wäre eine Entscheidung, die dem
    # Menschen gehört, der ihn deaktiviert hat.
    if not bester.kreditor.aktiv:
        return AbgleichErgebnis(kandidaten=kandidaten, anlass=ANLASS_FUZZY_NAME)

    if bester.match_typ in ('iban', 'iban_zweitkonto'):
        # IBAN trifft. Passt der Name grob dazu, ist das ein sicherer Treffer.
        if not name or aehnlichkeit(name, bester.kreditor.name) >= DUBLETTEN_SCHWELLE:
            return AbgleichErgebnis(kreditor=bester.kreditor)
        return AbgleichErgebnis(kandidaten=kandidaten, anlass=ANLASS_NAME_ABWEICHUNG)

    if bester.match_typ == 'name_exakt':
        # Name stimmt exakt. Ohne IBAN auf dem Beleg ist das der bisherige
        # Normalfall und bleibt ein sicherer Treffer.
        if not iban or gleiche_iban(bester.kreditor, iban):
            return AbgleichErgebnis(kreditor=bester.kreditor)
        return AbgleichErgebnis(kandidaten=kandidaten, anlass=ANLASS_IBAN_ABWEICHUNG)

    # Nur Ähnlichkeit — nie automatisch zuordnen.
    anlass = (
        ANLASS_IBAN_ABWEICHUNG
        if iban and bester.score >= NAME_IDENTISCH_SCHWELLE
        else ANLASS_FUZZY_NAME
    )
    return AbgleichErgebnis(kandidaten=kandidaten, anlass=anlass)
