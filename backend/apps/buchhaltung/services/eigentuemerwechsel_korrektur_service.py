"""
Service: Rückwirkender Eigentümerwechsel mit Sollstellungs-Korrektur (Spec v1.1).

Setzt KorrekturService v1.2 voraus.
A3 (Auszahlungs-Integration) ist noch nicht implementiert — kein auszahlung_service vorhanden.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.buchhaltung.models import (
    EigentuemerwechselVorgang,
    FrontofficeAufgabe,
    HausgeldSollstellung,
    WechselKorrekturPaar,
)
from apps.buchhaltung.services.korrektur_sollstellung_service import korrigiere_sollstellung


@transaction.atomic
def vorschau_erstellen(
    objekt,
    einheit,
    wechsel_datum,
    neueigentuemer_data: dict,
    user,
) -> EigentuemerwechselVorgang:
    """
    Erstellt den Vorgang im Status 'vorschau'. Berechnet Auszahlungsbetrag OHNE
    persistente Korrektur-Sollstellungen anzulegen.

    neueigentuemer_data: dict mit Schlüsseln vorname, nachname, anrede, email (optional)
    """
    from apps.personen.models import EigentumsVerhaeltnis

    if wechsel_datum.day != 1:
        raise ValidationError("Wechsel-Datum muss Monatserster sein.")

    try:
        voreigentuemer_ev = EigentumsVerhaeltnis.objects.get(
            einheit=einheit,
            ende__isnull=True,
        )
    except EigentumsVerhaeltnis.DoesNotExist:
        raise ValidationError("Keine aktive EigentumsVerhältnis für diese Einheit gefunden.")

    neueigentuemer_ev = _erstelle_oder_finde_neueigentuemer_ev(
        einheit=einheit,
        wechsel_datum=wechsel_datum,
        person_data=neueigentuemer_data,
        ende_initial=wechsel_datum,
    )

    vorgang = EigentuemerwechselVorgang.objects.create(
        objekt=objekt,
        einheit=einheit,
        voreigentuemer_ev=voreigentuemer_ev,
        neueigentuemer_ev=neueigentuemer_ev,
        wechsel_datum=wechsel_datum,
        meldedatum=timezone.localdate(),
        status='vorschau',
        erstellt_von=user,
        auszahlungsbetrag=Decimal('0.00'),
    )

    betroffene_originals = _ermittle_betroffene_perioden(voreigentuemer_ev, wechsel_datum)

    auszahlungsbetrag = Decimal('0.00')
    for original in betroffene_originals:
        auszahlungsbetrag += min(original.ist_betrag, original.soll_betrag)
        WechselKorrekturPaar.objects.create(
            wechsel_vorgang=vorgang,
            periode=original.periode,
            original_sollstellung=original,
            korrektur_sollstellung=None,
            neuanlage_sollstellung=None,
            original_ist_betrag_vor_korrektur=original.ist_betrag,
        )

    vorgang.auszahlungsbetrag = auszahlungsbetrag
    vorgang.save(update_fields=['auszahlungsbetrag'])

    return vorgang


@transaction.atomic
def vorschau_committen(
    vorgang: EigentuemerwechselVorgang,
    freigabe_user,
    auszahlungs_iban: str,
    auszahlung_unterdruecken: bool = False,
) -> EigentuemerwechselVorgang:
    """
    Vier-Augen-Freigabe. Erzeugt Korrekturen über generischen KorrekturService.

    EV-Lifecycle-Reihenfolge (wegen UniqueConstraint uniq_aktiver_vertrag_je_einheit):
      1. Voreigentümer.ende = wechsel_datum - 1 Tag
      2. Neueigentümer.ende = None
    """
    if freigabe_user.id == vorgang.erstellt_von_id:
        raise ValidationError("Freigabe-User muss von Ersteller verschieden sein.")
    if vorgang.status != 'vorschau':
        raise ValidationError(f"Status '{vorgang.status}' ist nicht freigabefähig.")

    paare = vorgang.korrektur_paare.select_related('original_sollstellung').order_by('periode')

    for paar in paare:
        korrektur, neuanlage = korrigiere_sollstellung(
            original=paar.original_sollstellung,
            neue_eigentumsverhaeltnis=vorgang.neueigentuemer_ev,
            neue_splits=None,
            korrektur_grund='eigentuemerwechsel',
            korrektur_vorgang_id=vorgang.id,
            user=freigabe_user,
        )
        paar.korrektur_sollstellung = korrektur
        paar.neuanlage_sollstellung = neuanlage
        paar.save(update_fields=['korrektur_sollstellung', 'neuanlage_sollstellung'])

    vorgang.status = 'freigegeben'
    vorgang.freigegeben_von = freigabe_user
    vorgang.freigegeben_am = timezone.now()
    vorgang.auszahlungs_iban = auszahlungs_iban
    vorgang.auszahlung_unterdruecken = auszahlung_unterdruecken
    vorgang.save()

    # EV-Lifecycle — Reihenfolge wegen UniqueConstraint kritisch
    vorgang.voreigentuemer_ev.ende = vorgang.wechsel_datum - timedelta(days=1)
    vorgang.voreigentuemer_ev.save(update_fields=['ende'])

    vorgang.neueigentuemer_ev.ende = None
    vorgang.neueigentuemer_ev.save(update_fields=['ende'])

    # A3 (Auszahlungs-Service) nicht implementiert — kein auszahlung_service vorhanden

    _erzeuge_frontoffice_aufgabe_neueigentuemer(vorgang)

    return vorgang


# ---------------------------------------------------------------------------
# Interne Helpers
# ---------------------------------------------------------------------------

def _ermittle_betroffene_perioden(voreigentuemer_ev, wechsel_datum):
    """Liefert alle committeten, nicht-neutralisierten, nicht-stornierten
    hausgeld-Sollstellungen des Voreigentümers ab wechsel_datum."""
    return HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=voreigentuemer_ev,
        sollstellungs_typ='hausgeld',
        periode__gte=wechsel_datum,
        storniert_am__isnull=True,
        neutralisiert_durch_opos__isnull=True,
        sollstellungslauf__status='commited',
    ).order_by('periode')


def _erstelle_oder_finde_neueigentuemer_ev(einheit, wechsel_datum, person_data: dict, ende_initial):
    from apps.personen.models import EigentumsVerhaeltnis
    person = _finde_oder_erstelle_person(person_data)
    return EigentumsVerhaeltnis.objects.create(
        einheit=einheit,
        person=person,
        beginn=wechsel_datum,
        ende=ende_initial,
    )


def _finde_oder_erstelle_person(person_data: dict):
    from apps.personen.models import Person
    email = person_data.get('email', '').strip()
    if email:
        existing = Person.objects.filter(email=email, person_typ='100').first()
        if existing:
            return existing
    iban = person_data.get('iban', '').strip()
    if iban:
        existing = Person.objects.filter(ibans__contains=[iban], person_typ='100').first()
        if existing:
            return existing
    return Person.objects.create(
        person_typ='100',
        anrede=person_data.get('anrede', ''),
        vorname=person_data.get('vorname', ''),
        nachname=person_data.get('nachname', ''),
        email=email,
    )


def _erzeuge_frontoffice_aufgabe_neueigentuemer(vorgang: EigentuemerwechselVorgang) -> None:
    paare = vorgang.korrektur_paare.select_related('neuanlage_sollstellung')
    neuanlage_betrag = sum(
        paar.neuanlage_sollstellung.soll_betrag
        for paar in paare
        if paar.neuanlage_sollstellung_id is not None
    )
    person = vorgang.neueigentuemer_ev.person
    FrontofficeAufgabe.objects.create(
        objekt=vorgang.objekt,
        aufgabe_typ='eigentuemerwechsel_forderung',
        beschreibung=(
            f"Neueigentümer {person.name} schuldet {neuanlage_betrag} € "
            f"rückwirkende Hausgeld-Forderung "
            f"(Einheit {vorgang.einheit.einheit_nr}, ab {vorgang.wechsel_datum})."
        ),
        ev_id=vorgang.neueigentuemer_ev.id,
        einheit_nr=vorgang.einheit.einheit_nr,
        erstellt_von=vorgang.freigegeben_von,
    )
