"""
Jahresabrechnung — Freigabe & Nebenbuch-Anbindung, Wizard-Schritt 8
(HGA-Spec v1.0 Kap. 6).

Atomarer Ablauf (Kap. 6.1):
1. Validierung: Status 'entwurf', Vollständigkeit (Kap. 7)
2. PDFs final rendern + als Dokument persistieren
3. sollstellungslauf_service.run_abrechnungsergebnis() — erzeugt
   HausgeldSollstellung(typ='abrechnungsergebnis') je Einheit mit Ergebnis != 0.
   KEINE Sachkontenbuchung (Kap. 6.3).
4. EinzelAbrechnungen mit den erzeugten Sollstellungen verknüpfen
5. Jahresabrechnung sperren (Status 'gesperrt', unveränderlich)

Was hier bewusst NICHT passiert (Kap. 6.3):
- kein Auszahlungslauf für Guthaben (separater, manueller Folgeschritt)
- keine Sachkontenbuchung Soll XXXX.950 / Haben Ausgleichskonto
- kein PDF-Versand an Eigentümer

Hinweis: Die PDF-Dateien selbst liegen im Storage und werden bei einem
Transaktions-Rollback nicht entfernt — nur die Dokument-Datensätze.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import Jahresabrechnung
from apps.buchhaltung.services import sollstellungslauf_service

from . import pdf_service


@transaction.atomic
def freigebe_jahresabrechnung(ja: Jahresabrechnung, user) -> Jahresabrechnung:
    """
    Schritt 8: sperrt die Jahresabrechnung, erzeugt PDFs final und ruft
    den Sollstellungslauf für 'abrechnungsergebnis' auf.
    """
    if ja.status != 'entwurf':
        raise ValidationError(
            "Nur Abrechnungen im Status 'entwurf' können freigegeben werden."
        )

    einzelabrechnungen = list(
        ja.einzelabrechnungen.select_related('einheit', 'eigentumsverhaeltnis', 'eigentuemer')
    )
    _validiere_vollstaendigkeit(ja, einzelabrechnungen)

    # 1. PDFs final rendern + als Dokument persistieren
    for ea in einzelabrechnungen:
        dokument = pdf_service.rendere_und_speichere(ea, user=user)
        ea.dokument = dokument
        ea.save(update_fields=['dokument'])

    # 2. Sollstellungslauf aufrufen — NICHT direkt Buchung erzeugen
    lauf = sollstellungslauf_service.run_abrechnungsergebnis(
        objekt=ja.objekt, wj=ja.wirtschaftsjahr, user=user,
    )

    # 3. EinzelAbrechnungen mit erzeugter Sollstellung verknüpfen
    #    (Ergebnis == 0 hat bewusst keine Sollstellung, Kap. 6.2)
    sollstellungen = {
        ss.eigentumsverhaeltnis_id: ss for ss in lauf.sollstellungen.all()
    }
    for ea in einzelabrechnungen:
        ss = sollstellungen.get(ea.eigentumsverhaeltnis_id)
        if ea.abrechnungsergebnis != 0 and ss is None:
            raise ValidationError(
                f"Einheit {ea.einheit.einheit_nr}: Sollstellung wurde nicht erzeugt — "
                f"Freigabe abgebrochen."
            )
        if ss is not None:
            ea.sollstellung = ss
            ea.save(update_fields=['sollstellung'])

    # 4. Jahresabrechnung sperren
    ja.status = 'gesperrt'
    ja.freigegeben_am = timezone.now()
    ja.freigegeben_von = user
    ja.sollstellungslauf = lauf
    ja.save(update_fields=[
        'status', 'freigegeben_am', 'freigegeben_von', 'sollstellungslauf',
    ])
    return ja


def _validiere_vollstaendigkeit(ja: Jahresabrechnung, einzelabrechnungen: list) -> None:
    """
    Kap. 7: Jede Einheit des Objekts hat eine EinzelAbrechnung, und keine
    EinzelAbrechnung hat ungeklärte Verteilerschlüssel-Fehler (Schritt 6).
    (Einheit hat kein aktiv-Flag — es zählen alle Einheiten des Objekts,
    siehe Phase-0-Doku.)
    """
    erwartete = set(ja.objekt.einheiten.values_list('id', flat=True))
    vorhandene = {ea.einheit_id for ea in einzelabrechnungen}
    fehlende = erwartete - vorhandene
    if fehlende:
        nummern = list(
            ja.objekt.einheiten.filter(id__in=fehlende)
            .values_list('einheit_nr', flat=True)
        )
        raise ValidationError(
            f"Fehlende Einzelabrechnungen für Einheiten: {', '.join(sorted(nummern))}"
        )
    fehlerhafte = [ea for ea in einzelabrechnungen if ea.positionen_hat_fehler()]
    if fehlerhafte:
        nummern = ', '.join(sorted(ea.einheit.einheit_nr for ea in fehlerhafte))
        raise ValidationError(
            f"Einzelabrechnungen mit ungeklärten Verteilerschlüssel-Fehlern: {nummern}"
        )
