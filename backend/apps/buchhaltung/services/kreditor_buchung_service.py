"""
Kreditorische Buchungen aus der Dialogbuchhaltung — Kontierung der
Kreditor-Seite.

Problem: Die Dialogbuchhaltung schickt die Kreditor-Seite nur als
`kreditor`-Fremdschlüssel, ohne Sachkonto. Die Rechnungslogik
(rechnung_op_service) bucht dagegen gegen das echte Kreditorkonto 70xxx.
Ohne Sachkonto fehlt das Kreditor-Bein im Hauptbuch: die Buchung erscheint
weder auf dem Kreditor-Kontoauszug noch in der Summen- und Saldenliste, und
das Kontoblatt des Wirtschaftsjahres ist unvollständig.

Dieser Service ergänzt das fehlende Bein. Die Seite ergibt sich daraus,
welches Sachkonto fehlt:

  Zahlungsausgang: soll_konto leer, haben_konto = Bank  → 70xxx ins Soll
  Zahlungseingang: soll_konto = Bank, haben_konto leer  → 70xxx ins Haben

Das Konto wird im Wirtschaftsjahr der Gegenseite aufgelöst. Konten sind
jahresgebunden — beide Beine einer Buchung müssen im selben Kontenrahmen
liegen, sonst zerfällt die Buchung auf zwei Jahre.
"""
from django.core.exceptions import ValidationError


def _jahr_bestimmen(gegenkonto, wirtschaftsjahr, buchungsdatum):
    """
    Zieljahr für das Kreditorkonto. Vorrang hat das Wirtschaftsjahr der
    Gegenseite — nur so liegen beide Beine im selben Kontenrahmen.
    """
    if gegenkonto is not None and gegenkonto.wirtschaftsjahr_id:
        return gegenkonto.wirtschaftsjahr.jahr
    if wirtschaftsjahr is not None:
        return wirtschaftsjahr.jahr
    if buchungsdatum is not None:
        return buchungsdatum.year
    return None


def kreditorkonto_ergaenzen(attrs: dict, instance=None) -> dict:
    """
    Ergänzt in den validierten Serializer-Daten das Kreditorkonto (70xxx)
    auf der Seite, die kein Sachkonto trägt. Gibt `attrs` zurück.

    Unangetastet bleiben:
      - Buchungen ohne Kreditor
      - Personenkontobuchungen (dort ist der Kreditor nur ein Vermerk)
      - Buchungen, die beide Sachkonten schon tragen (Rechnungslogik,
        E-Banking, Saldovortrag)
      - Buchungen ohne jedes Sachkonto — dort ist die Seite nicht
        ableitbar; hier wird nichts geraten.
    """
    from apps.rechnungen.services.rechnung_op_service import (
        get_or_create_kreditor_konto,
    )

    def wert(feld):
        if feld in attrs:
            return attrs[feld]
        return getattr(instance, feld, None) if instance is not None else None

    kreditor = wert('kreditor')
    if kreditor is None or wert('personenkonto') is not None:
        return attrs

    soll = wert('soll_konto')
    haben = wert('haben_konto')
    # Beide gesetzt oder beide leer → keine eindeutige Kreditor-Seite
    if (soll is None) == (haben is None):
        return attrs

    objekt = wert('objekt')
    if objekt is None:
        return attrs

    gegenkonto = haben if soll is None else soll
    jahr = _jahr_bestimmen(gegenkonto, wert('wirtschaftsjahr'), wert('buchungsdatum'))
    if jahr is None:
        return attrs

    konto = get_or_create_kreditor_konto(kreditor, objekt, jahr=jahr)
    if konto.wirtschaftsjahr_id and konto.wirtschaftsjahr.jahr != jahr:
        raise ValidationError(
            f'Kreditorkonto {konto.kontonummer} konnte im Wirtschaftsjahr {jahr} '
            f'nicht angelegt werden — bitte das Wirtschaftsjahr zuerst eröffnen.'
        )

    attrs['soll_konto' if soll is None else 'haben_konto'] = konto
    return attrs
