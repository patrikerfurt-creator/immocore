"""
Vorgang-Service (Phase B, Spec Vorgang & DMS Kap. 1.3 / 4).

Business-Logik rund um Anlage, Statuswechsel, Zuweisung und Kommentierung
eines ``Vorgang``. Statuswechsel laufen AUSSCHLIESSLICH über
``wechsle_status`` — nie durch direktes Setzen von ``Vorgang.status`` — damit
ungültige Übergänge und fehlende Audit-Einträge (``VorgangEreignis``)
ausgeschlossen sind (GoBD-Prinzip: keine stille Änderung).
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.vorgaenge.models import Vorgang, VorgangEreignis

# Erlaubte Statusübergänge (Spec Kap. 1.3). Terminal-Stati (erledigt,
# storniert) haben KEINEN Eintrag oder eine leere Zielmenge.
_ERLAUBTE_UEBERGAENGE = {
    'offen':          {'in_bearbeitung', 'storniert'},
    'in_bearbeitung': {'wartet_extern', 'wiedervorlage', 'erledigt', 'storniert'},
    'wartet_extern':  {'in_bearbeitung', 'erledigt', 'storniert'},
    'wiedervorlage':  {'in_bearbeitung', 'storniert'},
    'erledigt':       {'in_bearbeitung'},
    'storniert':      set(),
}

_GESCHLOSSENE_STATI = {'erledigt', 'storniert'}


@transaction.atomic
def erstelle_vorgang(*, typ, betreff, erstellt_von, quelle='manuell',
                      objekt=None, einheit=None, person=None,
                      beschreibung=None, prioritaet=None,
                      faellig_am=None, wiedervorlage_am=None,
                      zugewiesen_an=None, mail_referenz=None,
                      telefon_rufnummer=None, portal_sichtbar=False) -> Vorgang:
    """Legt einen neuen ``Vorgang`` an (Status immer ``offen``).

    ``prioritaet`` wird, sofern nicht übergeben, aus ``typ.standard_prioritaet``
    vorbelegt. Erzeugt bewusst KEIN ``VorgangEreignis`` — die Anlage ist über
    ``erstellt_am``/``erstellt_von`` am ``Vorgang`` selbst nachvollziehbar.
    """
    if prioritaet is None:
        prioritaet = typ.standard_prioritaet

    vorgang = Vorgang(
        typ=typ, quelle=quelle, betreff=betreff, beschreibung=beschreibung,
        objekt=objekt, einheit=einheit, person=person,
        prioritaet=prioritaet, faellig_am=faellig_am, wiedervorlage_am=wiedervorlage_am,
        zugewiesen_an=zugewiesen_an, mail_referenz=mail_referenz,
        telefon_rufnummer=telefon_rufnummer, portal_sichtbar=portal_sichtbar,
        erstellt_von=erstellt_von,
    )
    vorgang.full_clean()
    vorgang.save()

    # KI-Antwortvorschlag (Folgeauftrag): nur wenn am Typ aktiviert, und rein
    # asynchron (Celery) — die Vorgangsanlage darf niemals auf die KI warten
    # oder an ihr scheitern. Auslösung erst NACH erfolgreichem Commit, sonst
    # könnte der Task den Vorgang noch nicht in der DB finden.
    if typ.antwort_vorschlag_aktiv:
        from apps.vorgaenge.tasks import erzeuge_antwort_vorschlag
        transaction.on_commit(lambda: erzeuge_antwort_vorschlag.delay(str(vorgang.id)))

    return vorgang


@transaction.atomic
def wechsle_status(vorgang: Vorgang, neuer_status: str, *, erstellt_von,
                    kommentar: str | None = None, ereignis_typ: str = 'statuswechsel',
                    wiedervorlage_am=None) -> Vorgang:
    """Wechselt den Status eines ``Vorgang`` gemäß der Übergangstabelle (Kap. 1.3).

    - Ungültiger Übergang → ``ValidationError``, KEINE DB-Änderung (alle
      Prüfungen laufen VOR jeder Mutation am Vorgang).
    - ``erstellt_von`` darf nur ``None`` sein, wenn
      ``ereignis_typ='system_wiedervorlage_faellig'`` (automatische
      Wiedervorlage-Rückführung, Kap. 3).
    - Übergang NACH ``wiedervorlage``: ``wiedervorlage_am`` ist Pflicht-Parameter.
    - Verlassen von ``wiedervorlage`` (in beliebige Richtung): ``wiedervorlage_am``
      wird auf ``None`` zurückgesetzt (clean()-Regel: nur bei status='wiedervorlage' gesetzt).
    - Übergang NACH ``erledigt``/``storniert``: ``geschlossen_am``/``geschlossen_von`` gesetzt.
    - Wiedereröffnung (``erledigt`` → ``in_bearbeitung``): ``geschlossen_am``/
      ``geschlossen_von`` wieder auf ``None``.
    - Jeder (gültige) Wechsel erzeugt genau ein ``VorgangEreignis``.
    - Sichtbarkeit (Patrik-Entscheidung): ein von einem Mitarbeiter ausgelöster
      Statuswechsel (``ereignis_typ='statuswechsel'``) ist für den Eigentümer
      sichtbar (``intern=False``). Die automatische Wiedervorlage-Rückführung
      (``ereignis_typ='system_wiedervorlage_faellig'``) bleibt IMMER intern.
    - Läuft komplett in einer Transaktion.
    """
    alter_status = vorgang.status

    if neuer_status not in _ERLAUBTE_UEBERGAENGE.get(alter_status, set()):
        raise ValidationError(
            f"Statuswechsel von '{alter_status}' nach '{neuer_status}' ist nicht erlaubt."
        )
    if erstellt_von is None and ereignis_typ != 'system_wiedervorlage_faellig':
        raise ValidationError(
            "erstellt_von darf nur None sein, wenn "
            "ereignis_typ='system_wiedervorlage_faellig' ist."
        )
    if neuer_status == 'wiedervorlage' and wiedervorlage_am is None:
        raise ValidationError(
            "wiedervorlage_am ist beim Übergang nach 'wiedervorlage' Pflicht."
        )

    # Ab hier ausschließlich Mutationen — alle Validierungen sind bereits durch.
    vorgang.status = neuer_status

    if alter_status == 'wiedervorlage' and neuer_status != 'wiedervorlage':
        vorgang.wiedervorlage_am = None
    if neuer_status == 'wiedervorlage':
        vorgang.wiedervorlage_am = wiedervorlage_am

    if neuer_status in _GESCHLOSSENE_STATI:
        vorgang.geschlossen_am = timezone.now()
        vorgang.geschlossen_von = erstellt_von
    elif alter_status in _GESCHLOSSENE_STATI and neuer_status not in _GESCHLOSSENE_STATI:
        vorgang.geschlossen_am = None
        vorgang.geschlossen_von = None

    vorgang.full_clean()
    vorgang.save()

    # Sichtbarkeit richtet sich nach dem Auslöser, nicht nach einem Parameter,
    # damit hier niemand versehentlich ``intern=False`` für die automatische
    # Wiedervorlage-Rückführung setzen kann (Patrik-Entscheidung, siehe oben).
    intern = ereignis_typ == 'system_wiedervorlage_faellig'
    VorgangEreignis.objects.create(
        vorgang=vorgang, typ=ereignis_typ, text=kommentar,
        alter_wert=alter_status, neuer_wert=neuer_status, erstellt_von=erstellt_von,
        intern=intern,
    )
    return vorgang


@transaction.atomic
def weise_zu(vorgang: Vorgang, user, erstellt_von) -> Vorgang:
    """Ändert die Zuweisung (``zugewiesen_an``) eines ``Vorgang`` und protokolliert
    den alten/neuen Zuweisungs-User (Username oder ``None``) als ``VorgangEreignis``.

    Immer ``intern=True`` (Patrik-Entscheidung) — die Zuweisung ist eine rein
    interne Organisationsangelegenheit und geht den Eigentümer nichts an.
    """
    alter_wert = vorgang.zugewiesen_an.get_username() if vorgang.zugewiesen_an_id else None
    neuer_wert = user.get_username() if user is not None else None

    vorgang.zugewiesen_an = user
    vorgang.full_clean()
    vorgang.save()

    VorgangEreignis.objects.create(
        vorgang=vorgang, typ='zuweisung_geaendert',
        alter_wert=alter_wert, neuer_wert=neuer_wert, erstellt_von=erstellt_von,
        intern=True,
    )
    return vorgang


@transaction.atomic
def kommentiere(vorgang: Vorgang, text: str, erstellt_von, intern: bool = True) -> VorgangEreignis:
    """Legt einen Kommentar (``VorgangEreignis`` Typ ``kommentar``) an. Leerer
    Text wird abgewiesen.

    ``intern`` ist standardmäßig ``True`` (Patrik-Entscheidung): ein Kommentar
    ist ohne bewusstes Anhaken NIE für den Eigentümer sichtbar — ein Versehen
    bedeutet dadurch höchstens, dass der Eigentümer etwas nicht sieht, nie das
    Gegenteil (unwiderrufliche interne Kommunikation beim Kunden).
    """
    if not text or not text.strip():
        raise ValidationError("Kommentartext darf nicht leer sein.")

    return VorgangEreignis.objects.create(
        vorgang=vorgang, typ='kommentar', text=text, erstellt_von=erstellt_von,
        intern=intern,
    )


@transaction.atomic
def setze_portal_sichtbar(vorgang: Vorgang, sichtbar: bool) -> Vorgang:
    """Setzt ``Vorgang.portal_sichtbar`` — steuert AUSSCHLIESSLICH, ob der
    Vorgang für den Eigentümer überhaupt sichtbar ist (siehe
    ``portal_ansicht`` unten). Reine Sichtbarkeitssteuerung, kein
    inhaltlicher Eingriff in den Vorgang — anders als Status/Zuweisung/
    Kommentar erzeugt dies bewusst KEIN ``VorgangEreignis``.
    """
    vorgang.portal_sichtbar = bool(sichtbar)
    vorgang.full_clean()
    vorgang.save(update_fields=['portal_sichtbar'])
    return vorgang


def portal_ansicht(vorgang: Vorgang) -> dict:
    """Liefert genau das, was ein Eigentümer im (noch nicht existierenden)
    Portal sehen dürfte — Grundlage/Lesepfad, siehe Modul- und Auftrags-
    Dokumentation. Es gibt aktuell KEINEN öffentlichen Endpunkt und KEINEN
    Auth-Layer für Externe; dieser Lesepfad hängt hinter ``IsAuthenticated``
    und dient Mitarbeitern als Vorschau ("was sieht der Eigentümer?") sowie
    später dem Portal als Datenquelle.

    Ist ``vorgang.portal_sichtbar`` nicht gesetzt, wird ein klarer
    "nicht freigegeben"-Zustand zurückgegeben (``{'sichtbar': False}``) —
    KEINE inhaltlichen Daten.

    Enthält NUR Ereignisse mit ``intern=False``, chronologisch. Enthält
    NIEMALS ``zugewiesen_an``, interne Kommentartexte, KI-Entwürfe oder
    Kreditor-Kontaktdaten (die Ereignis-Filterung auf ``intern=False``
    stellt das für Kommentare/KI-Entwürfe automatisch sicher — die
    zurückgegebenen Vorgangsfelder unten enthalten ``zugewiesen_an`` schon
    grundsätzlich nicht).

    Dokumente: ``dokument_verknuepft``-Ereignisse liefern laut
    ``dokument_service.lade_dokument_hoch`` ausschließlich einen Freitext mit
    dem Dateinamen (``"Dokument hochgeladen: <dateiname>"``) — bewusst KEIN
    Datei-Link, KEINE Dokument-ID, KEIN Downloadpfad. Eine echte
    Dateifreigabe braucht ihren eigenen Mechanismus und ist NICHT Teil dieser
    Funktion.
    """
    if not vorgang.portal_sichtbar:
        return {'sichtbar': False}

    ereignisse = [
        {
            'typ': ereignis.typ,
            'typ_anzeige': ereignis.get_typ_display(),
            'text': ereignis.text,
            'erstellt_am': ereignis.erstellt_am,
        }
        for ereignis in vorgang.ereignisse.filter(intern=False).order_by('erstellt_am')
    ]

    return {
        'sichtbar': True,
        'nummer': vorgang.nummer,
        'betreff': vorgang.betreff,
        'beschreibung': vorgang.beschreibung,
        'status': vorgang.status,
        'status_anzeige': vorgang.get_status_display(),
        'erstellt_am': vorgang.erstellt_am,
        'objekt_bezeichnung': vorgang.objekt.bezeichnung if vorgang.objekt_id else None,
        'einheit_nr': vorgang.einheit.einheit_nr if vorgang.einheit_id else None,
        'ereignisse': ereignisse,
    }
