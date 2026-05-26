"""Wirtschaftsjahr-Service — Folgejahr-Eröffnung (Spec v1.0 Kap. 5)."""
from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.objekte.models import Wirtschaftsjahr, EinheitVerbrauch
from apps.konten.models import Konto, KontoVerteilerSchluessel


def folgejahr_preview(objekt_ids: list[str]) -> list[dict]:
    """Vorschau: Prüft je Objekt, ob ein Folgejahr angelegt werden kann."""
    from apps.objekte.models import Objekt

    ergebnisse = []
    for objekt_id in objekt_ids:
        try:
            objekt = Objekt.objects.get(pk=objekt_id)
        except Objekt.DoesNotExist:
            ergebnisse.append({
                'objekt_id': objekt_id,
                'status': 'fehler',
                'fehler': 'Objekt nicht gefunden.',
            })
            continue

        wj_letztes = (
            Wirtschaftsjahr.objects
            .filter(objekt_id=objekt_id)
            .order_by('-jahr')
            .first()
        )

        if wj_letztes is None:
            ergebnisse.append({
                'objekt_id': objekt_id,
                'objekt_nr': objekt.objektnummer,
                'bezeichnung': objekt.bezeichnung,
                'letztes_wj': None,
                'folgejahr': None,
                'status': 'fehler',
                'fehler': 'Kein Wirtschaftsjahr vorhanden — bitte WEG-Anlage-Wizard nutzen.',
            })
            continue

        jahr_neu = wj_letztes.jahr + 1
        exists = Wirtschaftsjahr.objects.filter(
            objekt_id=objekt_id, jahr=jahr_neu
        ).exists()

        if exists:
            ergebnisse.append({
                'objekt_id': objekt_id,
                'objekt_nr': objekt.objektnummer,
                'bezeichnung': objekt.bezeichnung,
                'letztes_wj': {'jahr': wj_letztes.jahr, 'status': wj_letztes.status},
                'folgejahr': jahr_neu,
                'status': 'fehler',
                'fehler': f'Folgejahr {jahr_neu} existiert bereits.',
            })
            continue

        ergebnisse.append({
            'objekt_id': objekt_id,
            'objekt_nr': objekt.objektnummer,
            'bezeichnung': objekt.bezeichnung,
            'letztes_wj': {'jahr': wj_letztes.jahr, 'status': wj_letztes.status},
            'folgejahr': jahr_neu,
            'status': 'ok',
            'fehler': None,
        })

    return ergebnisse


def folgejahr_eroeffnen_batch(objekt_ids: list[str], user) -> list[dict]:
    """Öffnet je Objekt ein Folgejahr. Fehler bei Objekt A blockieren Objekt B nicht."""
    ergebnisse = []
    for objekt_id in objekt_ids:
        try:
            with transaction.atomic():
                ergebnis = _folgejahr_eroeffnen_einzeln(objekt_id, user)
            ergebnisse.append(ergebnis)
        except Exception as exc:
            ergebnisse.append({
                'objekt_id': str(objekt_id),
                'status': 'fehler',
                'fehler': str(exc),
            })
    return ergebnisse


def _folgejahr_eroeffnen_einzeln(objekt_id: str, user) -> dict:
    wj_alt = (
        Wirtschaftsjahr.objects
        .filter(objekt_id=objekt_id)
        .order_by('-jahr')
        .first()
    )
    if wj_alt is None:
        raise ValidationError(
            'Kein Wirtschaftsjahr vorhanden — bitte WEG-Anlage-Wizard nutzen.'
        )

    jahr_neu = wj_alt.jahr + 1

    if Wirtschaftsjahr.objects.filter(objekt_id=objekt_id, jahr=jahr_neu).exists():
        raise ValidationError(f'Folgejahr {jahr_neu} existiert bereits.')

    wj_neu = Wirtschaftsjahr.objects.create(
        objekt_id=objekt_id,
        jahr=jahr_neu,
        beginn_monat=wj_alt.beginn_monat,
        status='offen',
        vorjahr=wj_alt,
        eroeffnet_von=user,
    )

    konten_kopiert     = _kopiere_konten(wj_alt, wj_neu)
    vs_kopiert         = _kopiere_vs_zuordnungen(wj_alt, wj_neu)
    verbrauch_kopiert  = _kopiere_einheit_verbrauch(wj_alt, wj_neu)

    return {
        'objekt_id':              str(objekt_id),
        'wj_neu':                 jahr_neu,
        'status':                 'ok',
        'konten_kopiert':         konten_kopiert,
        'vs_zuordnungen_kopiert': vs_kopiert,
        'verbrauchszeilen_kopiert': verbrauch_kopiert,
    }


def _kopiere_konten(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    """Kopiert alle Sachkonten des alten WJ in das neue WJ (neue UUIDs, keine Buchungen).

    Guard: Existieren im neuen WJ bereits Konten, wird nichts getan (Idempotenz).
    Damit ist sichergestellt, dass ein zweiter Aufruf (z.B. über den weg-vorlage-
    Endpoint) keine weiteren Duplikate erzeugt.

    Buchungen bleiben im jeweiligen WJ und zeigen auf die Konten desselben WJ —
    kein UUID-Mismatch über Jahresgrenzen hinweg.
    """
    if Konto.objects.filter(wirtschaftsjahr=wj_neu).exists():
        return 0  # bereits kopiert — nichts tun

    konten_alt = list(Konto.objects.filter(wirtschaftsjahr=wj_alt))
    neue_konten = [
        Konto(
            wirtschaftsjahr=wj_neu,
            kontonummer=k.kontonummer,
            kontoname=k.kontoname,
            abrechnungsart=k.abrechnungsart,
            direktes_buchen=k.direktes_buchen,
            verteilerschluessel=k.verteilerschluessel,
            kontoart=k.kontoart,
            arge_konto=k.arge_konto,
            arge_kostenart=k.arge_kostenart,
            aktiv=k.aktiv,
        )
        for k in konten_alt
    ]
    Konto.objects.bulk_create(neue_konten)
    return len(neue_konten)


def _kopiere_vs_zuordnungen(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    konten_map = {
        k.kontonummer: k.id
        for k in Konto.objects.filter(wirtschaftsjahr=wj_neu)
    }
    vs_alt = KontoVerteilerSchluessel.objects.filter(
        konto__wirtschaftsjahr=wj_alt
    ).select_related('konto')

    neue_vs = []
    for v in vs_alt:
        neue_konto_id = konten_map.get(v.konto.kontonummer)
        if neue_konto_id is None:
            continue
        neue_vs.append(KontoVerteilerSchluessel(
            konto_id=neue_konto_id,
            vs_code=v.vs_code,
            gueltig_ab=wj_neu.beginn_datum,
        ))
    KontoVerteilerSchluessel.objects.bulk_create(neue_vs)
    return len(neue_vs)


def _kopiere_einheit_verbrauch(wj_alt: Wirtschaftsjahr, wj_neu: Wirtschaftsjahr) -> int:
    verbrauch_alt = EinheitVerbrauch.objects.filter(wirtschaftsjahr=wj_alt)
    neue_verbrauch = [
        EinheitVerbrauch(
            wirtschaftsjahr=wj_neu,
            einheit=ev.einheit,
            vs_code=ev.vs_code,
            wert=None,
            einheit_text=ev.einheit_text,
            quelle=None,
        )
        for ev in verbrauch_alt
    ]
    EinheitVerbrauch.objects.bulk_create(neue_verbrauch)
    return len(neue_verbrauch)
