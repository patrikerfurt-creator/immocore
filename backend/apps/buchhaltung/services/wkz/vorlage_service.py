"""
WKZ Vorlage-Service — Anlage, Freigabe, Verwaltung von Wiederkehrenden Buchungs-Vorlagen.
"""
import logging
from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------

def validiere_split_kontonummer(kontonummer: str, objekt) -> None:
    """
    Prüft, dass die Kontonummer im Objekt existiert, im Aufwandsbereich liegt
    und ein aktives Standard- oder Unterkonto ist (keine Summierungskonten).
    """
    from apps.konten.models import Konto
    konto = Konto.objects.filter(
        wirtschaftsjahr__objekt=objekt,
        kontonummer=kontonummer,
        kontoart__in=['standard', 'unterkonto'],
        aktiv=True,
    ).first()
    if not konto:
        raise ValidationError(
            f"Konto {kontonummer} im Objekt nicht gefunden, inaktiv oder ein Summierungskonto."
        )
    if konto.direktes_buchen:
        raise ValidationError(
            f"Konto {kontonummer} ist direkt buchbar (direktes_buchen=True) — "
            f"nicht als WKZ-Split zulässig."
        )
    try:
        nr = int(kontonummer)
    except ValueError:
        raise ValidationError(f"Kontonummer '{kontonummer}' ist keine Zahl.")
    if not (50000 <= nr <= 55999):
        raise ValidationError(
            f"Konto {kontonummer} liegt außerhalb des Aufwandsbereichs (50000–55999)."
        )


def validiere_splits(vorlage) -> None:
    """SUM(splits.betrag) muss == vorlage.betrag_gesamt sein."""
    summe = sum(s.betrag for s in vorlage.splits.all())
    if abs(summe - vorlage.betrag_gesamt) > Decimal('0.01'):
        raise ValidationError(
            f"Split-Summe {summe} stimmt nicht mit betrag_gesamt "
            f"{vorlage.betrag_gesamt} überein (Differenz: {summe - vorlage.betrag_gesamt})."
        )


# ---------------------------------------------------------------------------
# Anlage
# ---------------------------------------------------------------------------

@transaction.atomic
def erstelle_vorlage(data: dict, splits_data: list[dict], user) -> 'WiederkehrendeBuchungVorlage':
    """
    Legt eine neue Vorlage mit Splits an. Status initial 'entwurf'.
    data: alle Vorlage-Felder außer id, status, erstellt_von, erstellt_am, geaendert_am
    splits_data: Liste von {kontonummer, bezeichnung, betrag, reihenfolge}
    """
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage, WiederkehrendeBuchungSplit
    from apps.objekte.models import Objekt
    from apps.rechnungen.models import Kreditor

    # UUIDs → Instanzen auflösen (Serializer liefert UUID-Objekte)
    if not isinstance(data.get('objekt'), Objekt):
        data['objekt'] = Objekt.objects.get(pk=data['objekt'])
    if not isinstance(data.get('kreditor'), Kreditor):
        data['kreditor'] = Kreditor.objects.get(pk=data['kreditor'])

    # Bescheid-Pflicht Default: True bei bescheid, False bei vertrag
    if 'bescheid_pflicht' not in data:
        data['bescheid_pflicht'] = (data.get('typ') == 'bescheid')

    vorlage = WiederkehrendeBuchungVorlage.objects.create(
        **data,
        status='entwurf',
        erstellt_von=user,
    )

    for i, s in enumerate(splits_data):
        WiederkehrendeBuchungSplit.objects.create(
            vorlage=vorlage,
            kontonummer=s['kontonummer'],
            bezeichnung=s['bezeichnung'],
            betrag=Decimal(str(s['betrag'])),
            reihenfolge=s.get('reihenfolge', i),
        )

    # Sofortige Volidierung
    validiere_splits(vorlage)
    for split in vorlage.splits.all():
        validiere_split_kontonummer(split.kontonummer, vorlage.objekt)

    # Aus Beleg angelegt: der Belegbezug wird nur gespeichert. Die Rechnung
    # bleibt im Rechnungseingang, bis die Buchhaltung die Erfassung abschließt
    # ('Geprüft → zur Freigabe'); erst dann verlässt sie den normalen Zahlweg
    # (siehe route_zur_freigabe → uebergib_rechnung_an_wkz).
    if vorlage.rechnung_id:
        logger.info(
            "WKZ Vorlage %s aus Rechnung %s angelegt — Rechnung bleibt bis zum "
            "Abschluss der Erfassung im Rechnungseingang",
            vorlage.id, vorlage.rechnung_id,
        )

    logger.info("WKZ Vorlage %s angelegt von %s", vorlage.id, user)
    return vorlage


def _rechnung_als_wkz_beleg_markieren(rechnung):
    """Nimmt die Rechnung aus dem normalen Zahlweg (status='wkz_beleg') und löst
    einen bereits angelegten Rechnungs-Kreditor-OP (Phase 1, unbezahlt,
    Buchung im Entwurf) auf, damit die Zahlung nicht doppelt läuft."""
    from apps.buchhaltung.models import KreditorOP, Buchung

    kop = KreditorOP.objects.filter(rechnung=rechnung).first()
    phase1 = kop.buchung if (kop and kop.status in ('offen', 'teilbezahlt')) else None
    if kop and kop.status in ('offen', 'teilbezahlt'):
        kop.delete()

    upd = ['status']
    rechnung.status = 'wkz_beleg'
    if phase1 is not None:
        for feld in ('op_buchung', 'aufwand_buchung', 'buchung'):
            if hasattr(rechnung, f'{feld}_id') and getattr(rechnung, f'{feld}_id') == phase1.id:
                setattr(rechnung, f'{feld}_id', None)
                upd.append(f'{feld}_id')
    rechnung.save(update_fields=upd)

    if phase1 is not None and phase1.status == 'entwurf':
        Buchung.objects.filter(parent_buchung=phase1).delete()
        phase1.delete()


@transaction.atomic
def uebergib_rechnung_an_wkz(rechnung, user=None):
    """Abschluss der Erfassung einer Rechnung, zu der eine WKZ-Vorlage besteht:
    die Zahlung läuft über die WKZ (mit eigener Freigabe), die Rechnung verlässt
    den normalen Zahlweg (status='wkz_beleg'). Wird aus route_zur_freigabe
    aufgerufen — nicht schon beim Anlegen der Vorlage."""
    _rechnung_als_wkz_beleg_markieren(rechnung)
    logger.info(
        "Rechnung %s nach Abschluss der Erfassung an die WKZ übergeben (durch %s)",
        rechnung.id, user,
    )
    return rechnung


@transaction.atomic
def verknuepfe_rechnung_als_wkz_beleg(vorlage, rechnung, user):
    """
    Verknüpft eine Eingangsrechnung als Beleg/Bescheid einer WKZ-Vorlage:
      - vorlage.rechnung = rechnung
      - Bescheid gilt als erbracht: offene WKZ-OPs verlassen 'bescheid_fehlt',
        bescheid_hochgeladen_am/von werden gesetzt.
      - Rechnung wird aus dem normalen Zahlweg genommen (status='wkz_beleg').
      - Ein bereits angelegter Kreditor-OP der Rechnung (Phase 1, unbezahlt,
        Buchung im Entwurf) wird aufgelöst, damit die Zahlung nicht doppelt läuft.
    """
    vorlage.rechnung = rechnung
    vorlage.save(update_fields=['rechnung'])

    jetzt = timezone.now()
    for op in vorlage.ops.all():
        felder = []
        if op.status == 'bescheid_fehlt':
            op.status = 'erzeugt'
            felder.append('status')
        if op.bescheid_hochgeladen_am is None:
            op.bescheid_hochgeladen_am = jetzt
            op.bescheid_hochgeladen_von = user
            felder += ['bescheid_hochgeladen_am', 'bescheid_hochgeladen_von']
        if felder:
            op.save(update_fields=felder)

    _rechnung_als_wkz_beleg_markieren(rechnung)
    logger.info("Rechnung %s als WKZ-Beleg mit Vorlage %s verknüpft", rechnung.id, vorlage.id)
    return vorlage


# ---------------------------------------------------------------------------
# Freigabe-Workflow
# ---------------------------------------------------------------------------

def _bestimme_freigabestufe(objekt, jahresbetrag) -> dict:
    """
    Liest zahlungsfreigabe_grenzen aus dem Objekt-JSONField.
    Erwartet Liste: [{"bis": 500, "rolle": "auto"}, {"bis": 5000, "rolle": "sachbearbeiter"}, ...]
    Kein Limit / leeres Dict → automatische Freigabe.
    """
    grenzen = objekt.zahlungsfreigabe_grenzen
    if not grenzen or not isinstance(grenzen, list):
        return {'rolle': 'auto'}
    for grenze in sorted(grenzen, key=lambda g: float(g['bis']) if g.get('bis') is not None else float('inf')):
        bis = grenze.get('bis')
        if bis is None or (jahresbetrag is not None and jahresbetrag <= Decimal(str(bis))):
            return grenze
    # Über allen Grenzen → letzte Stufe
    return grenzen[-1] if grenzen else {'rolle': 'auto'}


@transaction.atomic
def reiche_vorlage_zur_freigabe_ein(vorlage_id, eingereicht_von) -> 'WiederkehrendeBuchungVorlage':
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage
    vorlage = WiederkehrendeBuchungVorlage.objects.select_for_update().get(pk=vorlage_id)
    if vorlage.status != 'entwurf':
        raise ValueError("Nur Vorlagen im Status 'entwurf' können eingereicht werden.")

    validiere_splits(vorlage)
    for split in vorlage.splits.all():
        validiere_split_kontonummer(split.kontonummer, vorlage.objekt)

    jahresbetrag = vorlage.jahresbetrag
    stufe = _bestimme_freigabestufe(vorlage.objekt, jahresbetrag)

    if stufe.get('rolle') == 'auto':
        aktiviere_vorlage(vorlage, freigegeben_von=eingereicht_von)
        logger.info("WKZ Vorlage %s automatisch freigegeben", vorlage.id)
    else:
        vorlage.status = 'eingereicht'
        vorlage.save(update_fields=['status'])
        logger.info(
            "WKZ Vorlage %s eingereicht — wartet auf Freigabe durch Rolle '%s' (Jahresbetrag: %s €)",
            vorlage.id, stufe.get('rolle'), jahresbetrag,
        )

    return vorlage


def aktiviere_vorlage(vorlage, freigegeben_von) -> None:
    vorlage.status = 'aktiv'
    vorlage.freigegeben_am = timezone.now()
    vorlage.freigegeben_von = freigegeben_von
    vorlage.freigabe_jahresbetrag = vorlage.jahresbetrag
    vorlage.save()
    logger.info(
        "WKZ Vorlage %s aktiviert (Jahresbetrag: %s €, Rhythmus: %s)",
        vorlage.id, vorlage.jahresbetrag, vorlage.rhythmus,
    )


# ---------------------------------------------------------------------------
# Statusübergänge
# ---------------------------------------------------------------------------

@transaction.atomic
def pausiere_vorlage(vorlage_id, grund: str, user) -> 'WiederkehrendeBuchungVorlage':
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage
    vorlage = WiederkehrendeBuchungVorlage.objects.select_for_update().get(pk=vorlage_id)
    if vorlage.status != 'aktiv':
        raise ValueError("Nur aktive Vorlagen können pausiert werden.")
    vorlage.status = 'pausiert'
    vorlage.save(update_fields=['status', 'geaendert_am'])
    logger.info("WKZ Vorlage %s pausiert von %s: %s", vorlage.id, user, grund)
    return vorlage


@transaction.atomic
def reaktiviere_vorlage(vorlage_id, user) -> 'WiederkehrendeBuchungVorlage':
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage
    vorlage = WiederkehrendeBuchungVorlage.objects.select_for_update().get(pk=vorlage_id)
    if vorlage.status != 'pausiert':
        raise ValueError("Nur pausierte Vorlagen können reaktiviert werden.")
    vorlage.status = 'aktiv'
    vorlage.save(update_fields=['status', 'geaendert_am'])
    logger.info("WKZ Vorlage %s reaktiviert von %s", vorlage.id, user)
    return vorlage


@transaction.atomic
def beende_vorlage(vorlage_id, gueltig_bis: date, grund: str, user) -> 'WiederkehrendeBuchungVorlage':
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage
    vorlage = WiederkehrendeBuchungVorlage.objects.select_for_update().get(pk=vorlage_id)
    if vorlage.status not in ('aktiv', 'pausiert'):
        raise ValueError("Nur aktive oder pausierte Vorlagen können beendet werden.")
    vorlage.gueltig_bis = gueltig_bis
    vorlage.status = 'beendet'
    vorlage.save(update_fields=['gueltig_bis', 'status', 'geaendert_am'])
    logger.info(
        "WKZ Vorlage %s beendet von %s (gueltig_bis: %s, Grund: %s)",
        vorlage.id, user, gueltig_bis, grund,
    )
    return vorlage


# ---------------------------------------------------------------------------
# Bescheidsänderung — neue Version
# ---------------------------------------------------------------------------

@transaction.atomic
def ersetze_vorlage(alte_vorlage_id, neue_daten: dict, neue_splits: list[dict], user):
    """
    Beendet die alte Vorlage und legt eine neue an (GoBD-konforme Versionierung).
    """
    from apps.buchhaltung.models import WiederkehrendeBuchungVorlage, WiederkehrendeBuchungSplit

    alt = WiederkehrendeBuchungVorlage.objects.select_for_update().get(pk=alte_vorlage_id)
    if alt.status not in ('aktiv', 'pausiert'):
        raise ValueError("Nur aktive oder pausierte Vorlagen können ersetzt werden.")

    neue_erste_periode = neue_daten['gueltig_ab']
    if alt.gueltig_bis and alt.gueltig_bis < neue_erste_periode:
        raise ValueError("Alte Vorlage endet bereits vor Beginn der neuen.")

    # 1. Alte Vorlage beenden
    from datetime import timedelta
    alt.gueltig_bis = neue_erste_periode - timedelta(days=1)
    alt.status = 'beendet'
    alt.save(update_fields=['gueltig_bis', 'status', 'geaendert_am'])

    # 2. Neue Vorlage anlegen (Stammdaten aus alt, Differenzen übernehmen)
    neu = WiederkehrendeBuchungVorlage.objects.create(
        objekt=alt.objekt,
        kreditor=alt.kreditor,
        bezeichnung=neue_daten.get('bezeichnung', alt.bezeichnung),
        typ=alt.typ,
        betrag_gesamt=neue_daten['betrag_gesamt'],
        rhythmus=neue_daten.get('rhythmus', alt.rhythmus),
        erste_faelligkeit=neue_daten['erste_faelligkeit'],
        bei_wochenende=alt.bei_wochenende,
        vorlauf_tage=alt.vorlauf_tage,
        toleranz_betrag=alt.toleranz_betrag,
        toleranz_tage=alt.toleranz_tage,
        sepa_mandat_id=alt.sepa_mandat_id,
        bescheid_pflicht=alt.bescheid_pflicht,
        gueltig_ab=neue_erste_periode,
        gueltig_bis=neue_daten.get('gueltig_bis'),
        status='entwurf',
        ersetzt_vorlage=alt,
        erstellt_von=user,
    )

    # 3. Neue Splits anlegen
    for i, s in enumerate(neue_splits):
        WiederkehrendeBuchungSplit.objects.create(
            vorlage=neu,
            kontonummer=s['kontonummer'],
            bezeichnung=s['bezeichnung'],
            betrag=Decimal(str(s['betrag'])),
            reihenfolge=s.get('reihenfolge', i),
        )

    # 4. Freigabe-Workflow starten
    reiche_vorlage_zur_freigabe_ein(neu.id, eingereicht_von=user)

    logger.info(
        "WKZ Vorlage %s ersetzt durch %s (wirksam ab %s)",
        alt.id, neu.id, neue_erste_periode,
    )
    return neu
