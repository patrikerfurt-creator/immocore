"""
Jahresabrechnung — Berechnungslogik je Einheit, Wizard-Schritt 6
(HGA-Spec v1.0 Kap. 4.1/4.2/4.4).

Formel je Einheit (Kap. 4.1):

    Abrechnungsergebnis = Σ( Ist-Kosten_Konto_k × Anteil_Einheit_k )
                          − Hausgeld-Soll (aus dem Nebenbuch, Kap. 4.2)

- Hausgeld-Soll kommt aus HausgeldSollstellung (Typ 'hausgeld') — Soll-Prinzip,
  unabhängig vom Zahlungsstatus. Plan-Änderungen im Jahr und Nachhol-
  Sollstellungen aus Eigentümerwechseln sind darin bereits enthalten (Kap. 4.4).
- Adressat ist der Eigentümer zum Erstellungsdatum der Jahresabrechnung
  (Snapshot via eigentuemer-/eigentumsverhaeltnis-FK, Kap. 6.1).
- Verteilerschlüssel-Fehler brechen die Berechnung NICHT ab, sondern werden
  je Position mit 'fehler' in positionen geloggt — EinzelAbrechnung.
  positionen_hat_fehler() blockiert dann die Freigabe (Spec Kap. 7).

Abweichung zur Spec: Einheit hat kein aktiv-Flag — es werden alle Einheiten
des Objekts abgerechnet.

Schreibt: EinzelAbrechnung (Upsert je jahresabrechnung+einheit).
Manuelle Korrekturen (Schritt 6 UI) sind Phase E — eine Neuberechnung
überschreibt den Datensatz vollständig.
"""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum

from apps.buchhaltung.models import (
    EinzelAbrechnung,
    HausgeldSollstellung,
    Jahresabrechnung,
    SollstellungSplit,
)
from apps.konten.models import Konto
from apps.objekte.models import Einheit
from apps.personen.models import EigentumsVerhaeltnis

from .kostenstellen_service import kostenstellen_uebersicht
from .ruecklagen_service import ruecklagen_uebersicht
from .verteilerschluessel_service import (
    VERBRAUCH_VS_CODES,
    VerteilerschluesselFehler,
    aktiver_vs_code,
    alle_werte_und_gesamt,
    mea_anteil,
    mea_wert_und_gesamt,
)

ZWEI_STELLEN = Decimal('0.01')


def berechne_hausgeld_soll(ev: EigentumsVerhaeltnis, wj) -> Decimal:
    """
    Summe aller Hausgeld-Sollstellungen des EV im Wirtschaftsjahr —
    unabhängig vom Zahlungsstatus (Soll-Prinzip, nicht Ist; Spec Kap. 4.2).
    Enthält auch Nachhol-Sollstellungen aus Eigentümerwechsel.
    """
    return HausgeldSollstellung.objects.filter(
        eigentumsverhaeltnis=ev,
        sollstellungs_typ='hausgeld',
        periode__gte=wj.beginn_datum,
        periode__lte=wj.ende_datum,
        storniert_am__isnull=True,
    ).aggregate(summe=Sum('soll_betrag'))['summe'] or Decimal('0.00')


def berechne_ruecklagen_zufuehrung(ev: EigentumsVerhaeltnis, wj) -> Decimal:
    """
    Rücklagen-Zuführung des EV im WJ = Σ der Hausgeld-Sollstellungssplits mit
    einer Rücklagen-Buchungsart (BA 91x, bankkonto_typ='ruecklage_nach_index').

    Fließt zusätzlich zur Bewirtschaftung in die Abrechnungssumme ein (Kap. 4.1);
    der gleiche Betrag steckt als 911-Split bereits im Hausgeld-Soll und hebt
    sich dort auf — ein Ergebnis entsteht nur bei Abweichung Zuführung ≠ 911-Soll.
    Soll-Prinzip; muss lt. Wirtschaftsplan aufgehen.
    """
    return SollstellungSplit.objects.filter(
        sollstellung__eigentumsverhaeltnis=ev,
        sollstellung__sollstellungs_typ='hausgeld',
        sollstellung__periode__gte=wj.beginn_datum,
        sollstellung__periode__lte=wj.ende_datum,
        sollstellung__storniert_am__isnull=True,
        ba__bankkonto_typ='ruecklage_nach_index',
    ).aggregate(summe=Sum('betrag'))['summe'] or Decimal('0.00')


def _mea_bruch(wert, gesamt) -> str:
    """MEA als lesbarer Bruch „45/1000" (Spec Kap. 4: mea_anteil_einheit)."""
    def _z(v) -> str:
        return format(Decimal(str(v)).normalize(), 'f')
    return '%s/%s' % (_z(wert), _z(gesamt))


def berechne_rueckstand_ruecklage(ev: EigentumsVerhaeltnis, ba_nr: str, wj) -> Decimal:
    """
    Rückstand des Eigentümers auf die Zuführung zu EINER Rücklage (BA 91x) zum
    WJ-Ende: Soll (Sollstellungs-Split-Betrag) abzüglich tatsächlich gezahltem
    Betrag (SollstellungSplit.ist_betrag_split), kumuliert über alle Perioden
    bis WJ-Ende — analog zum objektweiten Hausgeldrückstand (pdf_service),
    hier aber je Rücklagen-BA aufgeschlüsselt.

    Rückstände auf die Erhaltungsrücklage sind gesondert auszuweisen
    (Kap. 4.5-Ergänzung) — Zuführungen stecken zwar auch im allgemeinen
    Hausgeld-Rückstand, aber dort nicht nach Rücklage getrennt.
    """
    return SollstellungSplit.objects.filter(
        sollstellung__eigentumsverhaeltnis=ev,
        sollstellung__sollstellungs_typ='hausgeld',
        sollstellung__periode__lte=wj.ende_datum,
        sollstellung__storniert_am__isnull=True,
        ba__nr=ba_nr,
    ).aggregate(s=Sum(F('betrag') - F('ist_betrag_split')))['s'] or Decimal('0')


def aktueller_eigentuemer(einheit: Einheit, stichtag) -> EigentumsVerhaeltnis:
    """
    EV, das zum Stichtag (Erstellungsdatum) aktiv ist (Spec Kap. 5 Schritt 6.1).
    Wirft ValidationError, wenn keines existiert — Datenfehler, blockiert Schritt 6.
    """
    ev = (
        EigentumsVerhaeltnis.objects
        .filter(einheit=einheit, beginn__lte=stichtag)
        .filter(Q(ende__isnull=True) | Q(ende__gte=stichtag))
        .select_related('person')
        .order_by('-beginn')
        .first()
    )
    if ev is None:
        raise ValidationError(
            f"Einheit {einheit.einheit_nr}: kein aktives Eigentumsverhältnis "
            f"zum Erstellungsdatum {stichtag} — Abrechnung nicht möglich."
        )
    return ev


def hat_eigentuemerwechsel_im_wj(einheit: Einheit, wj) -> bool:
    """Eigentümerwechsel im Abrechnungsjahr → Fußnote im PDF (Kap. 6.3)."""
    return EigentumsVerhaeltnis.objects.filter(
        Q(einheit=einheit),
        Q(ende__gte=wj.beginn_datum, ende__lte=wj.ende_datum)
        | Q(beginn__gt=wj.beginn_datum, beginn__lte=wj.ende_datum),
    ).exists()


def berechne_alle_einzelabrechnungen(ja: Jahresabrechnung) -> list:
    """
    Schritt 6: legt für jede Einheit des Objekts die EinzelAbrechnung an
    bzw. aktualisiert sie. Kostenstellen/Rücklagen werden einmal je Lauf
    aggregiert (kein N+1 über Einheiten).
    """
    if ja.status != 'entwurf':
        raise ValidationError("Einzelabrechnungen können nur im Status 'entwurf' berechnet werden.")
    if not ja.objekt.einheiten.exists():
        raise ValidationError(
            f"Objekt {ja.objekt.bezeichnung} hat keine Einheiten — "
            f"bitte zuerst Einheiten anlegen oder importieren."
        )

    wj = ja.wirtschaftsjahr
    einheiten = list(ja.objekt.einheiten.all().order_by('einheit_nr'))
    verteilung = _kostenverteilung(ja.objekt, wj, einheiten)
    ruecklagen = ruecklagen_uebersicht(ja.objekt, wj)

    ergebnisse = []
    for einheit in einheiten:
        ergebnisse.append(
            _berechne_einheit(ja, einheit, wj, verteilung, ruecklagen)
        )
    return ergebnisse


def berechne_einzelabrechnung(ja: Jahresabrechnung, einheit: Einheit) -> EinzelAbrechnung:
    """Einzelne Einheit neu berechnen (z.B. nach VS-Korrektur in Schritt 4)."""
    if ja.status != 'entwurf':
        raise ValidationError("Einzelabrechnungen können nur im Status 'entwurf' berechnet werden.")
    wj = ja.wirtschaftsjahr
    einheiten = list(ja.objekt.einheiten.all().order_by('einheit_nr'))
    return _berechne_einheit(
        ja, einheit, wj,
        _kostenverteilung(ja.objekt, wj, einheiten),
        ruecklagen_uebersicht(ja.objekt, wj),
    )


# ---------------------------------------------------------------------------
# intern
# ---------------------------------------------------------------------------

def _kostenverteilung(objekt, wj, einheiten) -> list:
    """
    Verteilt je Aufwandskonto (Ist-Kosten ≠ 0) die Kosten objektweit auf die
    Einheiten und gleicht Rundungsdifferenzen cent-genau aus, sodass
    Σ Anteile == Ist-Kosten je Konto (Restcent nach größtem Nachkommarest).

    Gibt je Position ein Dict zurück:
        konto, ist, vs_code, vs_fehler,
        werte:   {einheit_id: Wert},          # Verteilerbasis (PDF-Nachweis)
        gesamt:  Gesamtwert des VS,
        anteile: {einheit_id: Anteil},
        betraege:{einheit_id: gerundeter Betrag}
    Nicht am VS beteiligte Einheiten fehlen in werte/anteile/betraege und
    werden je Einheit als Fehler ausgewiesen (bestehendes Verhalten).
    """
    uebersicht = kostenstellen_uebersicht(objekt, wj)
    relevante = [p for p in uebersicht['positionen'] if p['ist'] != 0]
    konten = Konto.objects.in_bulk([p['konto_id'] for p in relevante])
    positionen = []
    for p in relevante:
        konto = konten[_uuid(p['konto_id'])]
        ist = p['ist']
        eintrag = {
            'konto': konto, 'ist': ist, 'vs_code': None, 'vs_fehler': None,
            'werte': {}, 'gesamt': None, 'anteile': {}, 'betraege': {},
        }
        try:
            vs_code = aktiver_vs_code(konto, stichtag=wj.ende_datum)
            werte, gesamt = alle_werte_und_gesamt(vs_code, objekt, wj)
        except VerteilerschluesselFehler as exc:
            eintrag['vs_fehler'] = exc.messages[0]
            positionen.append(eintrag)
            continue
        eintrag['vs_code'] = vs_code
        eintrag['werte'] = werte
        eintrag['gesamt'] = gesamt
        eintrag['anteile'] = {
            eid: (Decimal(w) / Decimal(gesamt)) for eid, w in werte.items()
        }
        if vs_code in VERBRAUCH_VS_CODES:
            # Verbrauchs-VS (Techem): der Wert je Einheit ist ein FESTER Betrag
            # (kein anteiliges Verteilen des Sammelkonto-Ist).
            eintrag['betraege'] = {eid: Decimal(w) for eid, w in werte.items()}
        else:
            eintrag['betraege'] = _apportioniere(ist, eintrag['anteile'])
        positionen.append(eintrag)
    return positionen


def _apportioniere(ist: Decimal, anteile: dict) -> dict:
    """
    Verteilt 'ist' im Verhältnis 'anteile' (Σ = 1) cent-genau auf die Einheiten.
    Größte-Reste-Verfahren: jede Einheit erhält den abgerundeten Cent-Anteil,
    die verbleibenden Cent gehen an die Einheiten mit dem größten Nachkommarest.
    Garantiert Σ Beträge == ist (auch bei negativem ist).
    """
    if not anteile:
        return {}
    cent = Decimal('0.01')
    ist_cents = int((ist / cent).to_integral_value(rounding=ROUND_HALF_UP))
    roh = {eid: Decimal(ist_cents) * anteil for eid, anteil in anteile.items()}
    boden = {eid: int(r.to_integral_value(rounding=ROUND_FLOOR)) for eid, r in roh.items()}
    rest = ist_cents - sum(boden.values())  # stets in [0, Anzahl Einheiten)
    reihenfolge = sorted(
        roh, key=lambda eid: (roh[eid] - boden[eid], str(eid)), reverse=True
    )
    ergebnis = {eid: Decimal(boden[eid]) * cent for eid in roh}
    for eid in reihenfolge[:rest]:
        ergebnis[eid] += cent
    return ergebnis


def _berechne_einheit(ja, einheit, wj, verteilung, ruecklagen) -> EinzelAbrechnung:
    ev = aktueller_eigentuemer(einheit, ja.erstellungsdatum)
    hausgeld_soll = berechne_hausgeld_soll(ev, wj)

    positionen_json = []
    kostenanteil = Decimal('0.00')
    for pos in verteilung:
        eintrag = {
            'kontonummer': pos['konto'].kontonummer,
            'kontoname': pos['konto'].kontoname,
            'gesamtkosten': str(pos['ist']),
            'vs_code': pos['vs_code'],
            'umlagefaehig': pos['konto'].umlagefaehig,
        }
        if pos['vs_fehler']:
            eintrag['fehler'] = pos['vs_fehler']
            positionen_json.append(eintrag)
            continue
        if einheit.id not in pos['betraege']:
            eintrag['fehler'] = 'Kein Verteilerschlüssel-Wert für die Einheit hinterlegt.'
            positionen_json.append(eintrag)
            continue
        anteil = pos['anteile'][einheit.id]
        betrag = pos['betraege'][einheit.id]
        eintrag['anteil'] = str(anteil.quantize(Decimal('0.000001')))
        eintrag['betrag'] = str(betrag)
        # Verteilerbasis (Wert der Einheit / Gesamtwert) für den PDF-Nachweis
        eintrag['wert'] = str(pos['werte'][einheit.id])
        eintrag['gesamt'] = str(pos['gesamt'])
        positionen_json.append(eintrag)
        kostenanteil += betrag

    ruecklagen_json = []
    for r in ruecklagen:
        eintrag = {
            'bezeichnung': r['bezeichnung'],
            'ba_nr': r['ba_nr'],
            'anfangsbestand': str(r['anfangsbestand']),
            'zufuehrungen': str(r['zufuehrungen']),
            'entnahmen': str(r['entnahmen']),
            'endbestand': str(r['endbestand_bank']),
            # Berechneter Endbestand + Klärungsfall-Flag (Kap. 4.5) — zusätzlich
            # zum tatsächlichen Bankauszug-Endbestand oben, für den PDF-Rücklagenspiegel
            # (siehe pdf_service._ruecklagenspiegel_kontext).
            'endbestand_berechnet': str(r['endbestand_berechnet']),
            'abweichung': str(r['abweichung']),
            'klaerungsfall': r['klaerungsfall'],
            # Rückstand des Eigentümers auf die Zuführung zu DIESER Rücklage
            # (Kap. 4.5-Ergänzung: Rückstände auf die Erhaltungsrücklage sind
            # auszuweisen) — siehe pdf_service._ruecklagenspiegel_kontext.
            'rueckstand_zufuehrung': str(berechne_rueckstand_ruecklage(ev, r['ba_nr'], wj)),
            # Ausweis-Metadaten fürs PDF (Spec Kap. 4)
            'suffix': r.get('suffix', r['ba_nr']),
            'nummer_roemisch': r.get('nummer_roemisch', ''),
        }
        try:
            anteil = mea_anteil(einheit, wj)
            # Anteil auf BEIDEN Basen (Spec Kap. 3.1 vs. Ist-Verhalten):
            # anteil_eigentuemer  -> Bankauszug-Endbestand, real vorhandenes
            #                        Geld und damit der maßgebliche Wert;
            # ..._berechnet       -> Anfangsbestand + Zuführungen - Entnahmen.
            # Ohne Klärungsfall identisch, im Klärungsfall zeigt das PDF beide.
            eintrag['anteil_eigentuemer'] = str(
                (r['endbestand_bank'] * anteil).quantize(ZWEI_STELLEN, rounding=ROUND_HALF_UP)
            )
            eintrag['anteil_eigentuemer_berechnet'] = str(
                (r['endbestand_berechnet'] * anteil).quantize(ZWEI_STELLEN, rounding=ROUND_HALF_UP)
            )
            wert, gesamt = mea_wert_und_gesamt(einheit, wj)
            eintrag['mea_anteil_einheit'] = _mea_bruch(wert, gesamt)
        except VerteilerschluesselFehler as exc:
            eintrag['fehler'] = exc.messages[0]
        ruecklagen_json.append(eintrag)

    # Rücklagenzuführung (BA 91x) fließt zusätzlich zur Bewirtschaftung in die
    # Abrechnungssumme ein (Kap. 4.1). Der 911-Split steckt zugleich im
    # Hausgeld-Soll und hebt sich dort auf.
    ruecklagen_zufuehrung = berechne_ruecklagen_zufuehrung(ev, wj)
    abrechnungssumme = kostenanteil + ruecklagen_zufuehrung
    abrechnungsergebnis = abrechnungssumme - hausgeld_soll

    ea, _ = EinzelAbrechnung.objects.update_or_create(
        jahresabrechnung=ja,
        einheit=einheit,
        defaults={
            'eigentuemer': ev.person,
            'eigentumsverhaeltnis': ev,
            'hausgeld_soll_gesamt': hausgeld_soll,
            'kostenanteil_gesamt': kostenanteil,
            'ruecklagen_zufuehrung_gesamt': ruecklagen_zufuehrung,
            'abrechnungsergebnis': abrechnungsergebnis,
            'positionen': positionen_json,
            'ruecklagen': ruecklagen_json,
            'hinweis_eigentuemerwechsel': hat_eigentuemerwechsel_im_wj(einheit, wj),
        },
    )
    return ea


def _uuid(value):
    from uuid import UUID
    return value if isinstance(value, UUID) else UUID(value)
