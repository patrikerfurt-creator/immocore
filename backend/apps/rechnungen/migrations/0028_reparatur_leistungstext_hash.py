"""
Zieht ``leistungstext_hash`` auf die aktuelle Hash-Formel nach.

``normalisiere_leistungstext`` entfernt seit dem Erkennungs-Fix auch
Monatsnamen — sonst bekommt eine Dauerleistung ("Verwaltergebühr für den
Monat August") jeden Monat einen neuen Hash, die gelernte Regel greift nie
wieder und stattdessen entsteht monatlich eine neue.

Die bereits gespeicherten Hashes wurden dabei nicht mitgezogen: jede Regel,
deren Leistungstext einen Monatsnamen enthält, trägt weiter den Wert nach
alter Formel und kann deshalb nie mehr matchen. Auf Live betraf das 8 von 27
aktiven Regeln — genau die Dauerleistungen (Verwaltergebühr, Hausmeister,
Gartenpflege), die der Fix schützen sollte.

Rekonstruiert wird bei Regeln aus ``leistungstext_sample`` (Original-Text der
ersten Bestätigung), bei Rechnungen aus dem Leistungstext selbst.

Sonderfall Zusammenfall: nach dem Wegfall der Monatsnamen können mehrere
Regeln desselben Kreditor/Objekt-Paars auf denselben Hash fallen — bei
Dauerleistungen ist das der beabsichtigte Effekt. Sie werden zu einer Regel
zusammengeführt (höchste Trefferzahl gewinnt, Trefferzahlen summiert), die
übrigen werden ``veraltet``. Zeigen sie auf verschiedene Aufwandskonten, ist
die Kontierung nicht mehr entscheidbar — dann veralten ALLE Regeln der
Gruppe, damit die Erkennung einen Prüffall liefert statt automatisch ein
womöglich falsches Konto zu setzen.

Achtung bei künftigen Änderungen an ``normalisiere_leistungstext``: die
Funktion wird hier importiert, nicht eingefroren (wie in 0027). Ein weiterer
Formelwechsel braucht deshalb eine eigene Migration.
"""
from collections import defaultdict

from django.db import migrations

from apps.rechnungen.recognition import leistungstext_hash


def _fuehrende_zuerst(regeln):
    """Stärkste Regel zuerst: meiste Treffer, dann tatsächlich angewandt,
    dann die älteste (sie trägt die länger gepflegte Kontierung)."""
    return sorted(
        regeln,
        key=lambda r: (-r.trefferzahl, r.letzte_anwendung is None, r.erstellt_am),
    )


def _regeln_reparieren(MatchRegel):
    gruppen = defaultdict(list)
    for regel in MatchRegel.objects.filter(status='aktiv'):
        sample = (regel.leistungstext_sample or '').strip()
        if not sample:
            # Ohne Original-Text ist der Hash nicht rekonstruierbar — die
            # Regel bleibt unangetastet.
            continue
        schluessel = (regel.kreditor_id, regel.objekt_id, leistungstext_hash(sample))
        gruppen[schluessel].append(regel)

    neuer_hash = {}      # regel -> Zielhash
    zu_veralten = []

    for (_, _, ziel_hash), regeln in gruppen.items():
        if len(regeln) == 1:
            regel = regeln[0]
            if regel.leistungstext_hash != ziel_hash:
                neuer_hash[regel] = ziel_hash
            continue

        if len({r.aufwandskonto_id for r in regeln}) > 1:
            zu_veralten.extend(regeln)
            continue

        fuehrend, *rest = _fuehrende_zuerst(regeln)
        fuehrend.trefferzahl = sum(r.trefferzahl for r in regeln)
        neuer_hash[fuehrend] = ziel_hash
        zu_veralten.extend(rest)

    # Reihenfolge ist wichtig: erst veralten, sonst kollidiert ein neuer Hash
    # mit ``unique_aktive_matchregel``.
    if zu_veralten:
        for regel in zu_veralten:
            regel.status = 'veraltet'
        MatchRegel.objects.bulk_update(zu_veralten, ['status'], batch_size=500)

    if not neuer_hash:
        return 0

    # Zwei Phasen über einen eindeutigen Platzhalter: ein Zielhash kann der
    # Altwert einer anderen Regel desselben Paars sein, und die Unique-
    # Constraint greift auch bei nur vorübergehender Doppelung.
    for regel in neuer_hash:
        regel.leistungstext_hash = f'tmp-{regel.pk}'
    MatchRegel.objects.bulk_update(list(neuer_hash), ['leistungstext_hash'], batch_size=500)

    for regel, ziel_hash in neuer_hash.items():
        regel.leistungstext_hash = ziel_hash
    MatchRegel.objects.bulk_update(
        list(neuer_hash), ['leistungstext_hash', 'trefferzahl'], batch_size=500,
    )
    return len(neuer_hash)


def _rechnungen_reparieren(Rechnung):
    """Das Feld an der Rechnung ist reiner Vergleichs-Cache, wird aber nur
    neu gesetzt, wenn Kreditor UND Objekt eindeutig erkannt sind — sonst
    bleibt der Altwert stehen und verfälscht den Regelvergleich."""
    zu_speichern = []
    bestand = (
        Rechnung.objects
        .exclude(leistungstext_hash='')
        .exclude(leistungstext_hash__isnull=True)
        .only('id', 'leistungstext', 'leistungsbeschreibung', 'leistungstext_hash')
    )
    for rechnung in bestand:
        text = rechnung.leistungstext or rechnung.leistungsbeschreibung or ''
        if not text.strip():
            continue
        ziel = leistungstext_hash(text)
        if ziel != rechnung.leistungstext_hash:
            rechnung.leistungstext_hash = ziel
            zu_speichern.append(rechnung)

    Rechnung.objects.bulk_update(zu_speichern, ['leistungstext_hash'], batch_size=500)
    return len(zu_speichern)


def neu_berechnen(apps, schema_editor):
    _regeln_reparieren(apps.get_model('rechnungen', 'RechnungsMatchRegel'))
    _rechnungen_reparieren(apps.get_model('rechnungen', 'Rechnung'))


def zurueck(apps, schema_editor):
    """Kein echtes Zurück: die alten Hashes stammen aus einer Formel, die es
    im Code nicht mehr gibt, und sind nicht rekonstruierbar. Der Hash ist
    reine Vergleichshilfe und jederzeit aus dem Leistungstext ableitbar — ein
    No-Op verliert hier nichts. Zusammengeführte Regeln bleiben allerdings
    ``veraltet``; das ist gewollt, ein Rückbau würde die Doppelregeln
    wiederbeleben."""


class Migration(migrations.Migration):

    dependencies = [
        ('rechnungen', '0027_normalisiere_kreditornamen'),
    ]

    operations = [
        migrations.RunPython(neu_berechnen, zurueck),
    ]
