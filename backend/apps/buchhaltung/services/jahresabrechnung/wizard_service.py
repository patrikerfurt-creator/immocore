"""
Jahresabrechnung — Wizard-Ablauf (HGA-Spec v1.0 Kap. 5 + 9).

Ergänzt die Spec-Architektur (Kap. 8) um den Wizard-Kleber: Anlage
(Schritt 1), Buchungsprüfung (Schritt 2), Schritt-Navigation über die
Prozess-Engine, Umlageschlüssel-Korrektur (Schritt 4) und manuelle
Einzelabrechnungs-Korrektur (Schritt 6). Views rufen ausschließlich
diese Funktionen auf — keine Geschäftslogik in Views (Kap. 14).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.buchhaltung.models import (
    EigentuemerwechselVorgang,
    EinzelAbrechnung,
    Jahresabrechnung,
    KreditorOP,
    WiederkehrendeBuchungOP,
)
from apps.konten.models import Konto, KontoVerteilerSchluessel
from apps.objekte.models import Objekt, Wirtschaftsjahr
from apps.prozesse.models import Prozess

ANZAHL_SCHRITTE = 8


# ---------------------------------------------------------------------------
# Schritt 1 — Jahr & Objekt
# ---------------------------------------------------------------------------

@transaction.atomic
def erstelle_jahresabrechnung(objekt: Objekt, wj: Wirtschaftsjahr, user) -> Jahresabrechnung:
    """
    Legt Prozess + Jahresabrechnung (entwurf) an. Existiert bereits ein
    Entwurf für Objekt+WJ, wird dieser fortgesetzt (Wizard unterbrechbar).
    Eine Abrechnung mit Status != entwurf blockiert (Kap. 5 Schritt 1).
    """
    if wj.objekt_id != objekt.id:
        raise ValidationError("Wirtschaftsjahr gehört nicht zum gewählten Objekt.")
    if wj.status != 'offen':
        raise ValidationError(
            f"Wirtschaftsjahr {wj.jahr} ist nicht offen — Jahresabrechnung nicht möglich."
        )

    bestehende = (
        Jahresabrechnung.objects
        .filter(objekt=objekt, wirtschaftsjahr=wj)
        .exclude(status='storniert')
        .first()
    )
    if bestehende:
        if bestehende.status != 'entwurf':
            raise ValidationError(
                f"Für {objekt.bezeichnung} / WJ {wj.jahr} existiert bereits eine "
                f"Jahresabrechnung (Status: {bestehende.get_status_display()}). "
                f"Korrekturen erfordern eine Korrekturabrechnung (eigene Folgespec)."
            )
        return bestehende  # Entwurf fortsetzen

    prozess = Prozess.objects.create(
        prozess_typ='jahresabrechnung',
        objekt=objekt,
        gestartet_von=user,
        current_step=1,
    )
    return Jahresabrechnung.objects.create(
        objekt=objekt,
        wirtschaftsjahr=wj,
        prozess=prozess,
        erstellt_von=user,
    )


def eigentuemerwechsel_im_wj(objekt: Objekt, wj: Wirtschaftsjahr) -> list:
    """Hinweis-Banner Schritt 1: freigegebene Wechsel-Vorgänge im WJ-Zeitraum."""
    vorgaenge = (
        EigentuemerwechselVorgang.objects
        .filter(
            objekt=objekt, status='freigegeben',
            wechsel_datum__gte=wj.beginn_datum,
            wechsel_datum__lte=wj.ende_datum,
        )
        .select_related('einheit')
    )
    return [
        {
            'einheit_nr': v.einheit.einheit_nr,
            'wechsel_datum': v.wechsel_datum.isoformat(),
        }
        for v in vorgaenge
    ]


# ---------------------------------------------------------------------------
# Schritt 2 — Buchungsprüfung
# ---------------------------------------------------------------------------

def buchungspruefung(objekt: Objekt, wj: Wirtschaftsjahr) -> dict:
    """
    Offene Kreditoren-OPs (hartes Blocking, Kap. 5 Schritt 2) und offene
    WKZ-OPs im WJ. Blockiert = mind. ein offener/teilbezahlter Kreditor-OP
    mit Fälligkeit bis WJ-Ende.
    """
    kreditor_ops = (
        KreditorOP.objects
        .filter(
            objekt=objekt,
            status__in=['offen', 'teilbezahlt'],
            faellig_ab__lte=wj.ende_datum,
        )
        .select_related('kreditor')
        .order_by('faellig_ab')
    )
    wkz_ops = (
        WiederkehrendeBuchungOP.objects
        .filter(
            vorlage__objekt=objekt,
            status__in=['erzeugt', 'bescheid_fehlt'],
            faellig_am__lte=wj.ende_datum,
        )
        .select_related('vorlage')
        .order_by('faellig_am')
    )
    kreditor_liste = [
        {
            'op_nummer': op.op_nummer,
            'kreditor': str(op.kreditor),
            'betrag_offen': str(op.betrag_offen),
            'faellig_ab': op.faellig_ab.isoformat(),
            'status': op.status,
        }
        for op in kreditor_ops
    ]
    wkz_liste = [
        {
            'vorlage': op.vorlage.bezeichnung,
            'periode_von': op.periode_von.isoformat(),
            'periode_bis': op.periode_bis.isoformat(),
            'faellig_am': op.faellig_am.isoformat(),
            'status': op.status,
        }
        for op in wkz_ops
    ]
    return {
        'kreditor_ops': kreditor_liste,
        'wkz_ops': wkz_liste,
        'blockiert': len(kreditor_liste) > 0,
    }


# ---------------------------------------------------------------------------
# Schritt-Navigation (Prozess-Engine)
# ---------------------------------------------------------------------------

def setze_schritt(ja: Jahresabrechnung, schritt: int, daten: 'dict | None' = None) -> Prozess:
    """Persistiert Wizard-Zwischenstand in Prozess.steps_data + current_step."""
    if not 1 <= schritt <= ANZAHL_SCHRITTE:
        raise ValidationError(f"Ungültiger Schritt {schritt} (1–{ANZAHL_SCHRITTE}).")
    if ja.status != 'entwurf':
        raise ValidationError("Wizard-Navigation nur im Status 'entwurf' möglich.")
    prozess = ja.prozess
    if daten:
        steps_data = prozess.steps_data or {}
        steps_data[str(schritt)] = daten
        prozess.steps_data = steps_data
    prozess.current_step = schritt
    prozess.save(update_fields=['steps_data', 'current_step'])
    return prozess


# ---------------------------------------------------------------------------
# Schritt 4 — Umlageschlüssel-Korrektur
# ---------------------------------------------------------------------------

def korrigiere_umlageschluessel(ja: Jahresabrechnung, konto_id, vs_code: str) -> KontoVerteilerSchluessel:
    """
    Manuelle VS-Korrektur nur für das aktuelle WJ, nicht rückwirkend
    (Kap. 5 Schritt 4): Zuordnung mit gueltig_ab = WJ-Beginn wird
    angelegt/überschrieben — frühere Zuordnungen bleiben unberührt.
    """
    if ja.status != 'entwurf':
        raise ValidationError("VS-Korrektur nur im Status 'entwurf' möglich.")
    wj = ja.wirtschaftsjahr
    try:
        konto = Konto.objects.get(id=konto_id, wirtschaftsjahr=wj)
    except Konto.DoesNotExist:
        raise ValidationError("Konto gehört nicht zum Wirtschaftsjahr der Abrechnung.")
    zuordnung, _ = KontoVerteilerSchluessel.objects.update_or_create(
        konto=konto,
        gueltig_ab=wj.beginn_datum,
        defaults={'vs_code': vs_code},
    )
    return zuordnung


def vs_zuordnung_neu_einlesen(ja: Jahresabrechnung) -> dict:
    """
    Schritt 4: VS-Zuordnung je Konto neu aus dem Kontenrahmen einlesen.

    Materialisiert die Umlageschlüssel-Zuordnung des Wirtschaftsjahres frisch
    aus dem Feld ``Konto.verteilerschluessel`` (Kontenrahmen). Bestehende
    WJ-Zuordnungen (KontoVerteilerSchluessel) werden dabei ersetzt — so werden
    veraltete manuelle Zuordnungen auf den aktuellen Kontenrahmen zurückgesetzt.
    """
    if ja.status != 'entwurf':
        raise ValidationError("VS neu einlesen ist nur im Status 'entwurf' möglich.")
    wj = ja.wirtschaftsjahr
    konten = list(Konto.objects.filter(wirtschaftsjahr=wj))
    KontoVerteilerSchluessel.objects.filter(konto__in=konten).delete()
    neue = [
        KontoVerteilerSchluessel(konto=k, gueltig_ab=wj.beginn_datum, vs_code=k.verteilerschluessel)
        for k in konten if k.verteilerschluessel
    ]
    KontoVerteilerSchluessel.objects.bulk_create(neue)
    return {'konten_gesamt': len(konten), 'zugeordnet': len(neue)}


# ---------------------------------------------------------------------------
# Schritt 6 — manuelle Korrektur einer Einzelabrechnung
# ---------------------------------------------------------------------------

def korrigiere_einzelabrechnung(
    ea: EinzelAbrechnung, positionen: list, grund: str, user,
) -> EinzelAbrechnung:
    """
    Manuelle Korrektur schreibt in positionen mit Änderungsvermerk
    (manuell_korrigiert: true, grund — Kap. 5 Schritt 6) und rechnet
    kostenanteil_gesamt/abrechnungsergebnis aus den Positionen neu.
    """
    if ea.jahresabrechnung.status != 'entwurf':
        raise ValidationError("Korrektur nur im Status 'entwurf' möglich.")
    if not grund or not grund.strip():
        raise ValidationError("Korrekturgrund ist Pflicht.")

    kostenanteil = Decimal('0.00')
    for pos in positionen:
        if pos.get('fehler'):
            continue
        try:
            kostenanteil += Decimal(str(pos['betrag']))
        except (KeyError, ArithmeticError, TypeError, ValueError):
            raise ValidationError(
                f"Position {pos.get('kontonummer', '?')}: ungültiger Betrag."
            )

    ea.positionen = positionen
    ea.kostenanteil_gesamt = kostenanteil
    ea.abrechnungsergebnis = kostenanteil - ea.hausgeld_soll_gesamt
    ea.save(update_fields=['positionen', 'kostenanteil_gesamt', 'abrechnungsergebnis'])

    prozess = ea.jahresabrechnung.prozess
    steps_data = prozess.steps_data or {}
    korrekturen = steps_data.setdefault('6_korrekturen', [])
    korrekturen.append({
        'einheit_id': str(ea.einheit_id),
        'manuell_korrigiert': True,
        'grund': grund.strip(),
        'user': user.username,
        'datum': date.today().isoformat(),
    })
    prozess.steps_data = steps_data
    prozess.save(update_fields=['steps_data'])
    return ea
