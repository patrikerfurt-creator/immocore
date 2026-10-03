"""
Stimmgrundlage-Service (Spec v1.1 Kap. 2) — Verwaltung der ``EVStimmgrundlage``
einer EV: Ableitung aus den Legacy-Feldern (``stimmprinzip``/
``stimm_verteilerschluessel``) bei Anlage sowie Ergänzung weiterer
Stimmgrundlagen davor.

Bewusste Designentscheidung: ``ev_service.erstelle_ev`` behält seine
bestehende Aufrufsignatur (``stimmprinzip``/``stimm_verteilerschluessel``/
``stimm_wirtschaftsjahr``) unverändert bei — jede neu angelegte EV bekommt
darüber automatisch GENAU EINE (Standard-)Stimmgrundlage. Die in Spec v1.1
Kap. 2 beschriebene Mehrfachauswahl mehrerer Stimmgrundlagen bei EV-Anlage
läuft über zusätzliche Aufrufe von ``hinzufuegen()`` NACH ``erstelle_ev`` —
das vermeidet einen Breaking-Change an allen bestehenden Aufrufstellen von
``erstelle_ev`` (Tests, Views, Management-Commands) und bleibt trotzdem
spezifikationskonform, weil TOPs frühestens nach der EV-Anlage entstehen.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.versammlung.models import EVStimmgrundlage


def _bezeichnung(*, ist_kopfprinzip: bool, verteilerschluessel=None) -> str:
    if ist_kopfprinzip:
        return 'Kopfprinzip'
    return f'{verteilerschluessel.schluessel} {verteilerschluessel.bezeichnung}'.strip()


def _erzeuge_kopfprinzip(ev, *, ist_standard: bool) -> EVStimmgrundlage:
    return EVStimmgrundlage.objects.create(
        ev=ev, verteilerschluessel=None, ist_kopfprinzip=True,
        wirtschaftsjahr=0, ist_standard=ist_standard,
        bezeichnung_anzeige=_bezeichnung(ist_kopfprinzip=True),
    )


@transaction.atomic
def erzeuge_aus_legacy_feldern(ev) -> EVStimmgrundlage:
    """Legt die Stimmgrundlagen einer frisch angelegten EV an.

    Die (Standard-)Stimmgrundlage wird 1:1 aus ``ev.stimmprinzip``/
    ``ev.stimm_verteilerschluessel``/``ev.stimm_wirtschaftsjahr`` abgeleitet —
    genau die Grundlage, die ``stimmkraft_service`` bisher EV-weit verwendet
    hat. Gibt diese Standard-Grundlage zurück. Wird ausschließlich von
    ``ev_service.erstelle_ev`` aufgerufen.

    Das echte Kopfprinzip (§ 25 Abs. 2 WEG, eine Stimme je Person) muss bei
    jeder EV als Gewichtungsoption verfügbar sein. Ist die Standard-Grundlage
    ein Verteilerschlüssel (MEA/Objekt), wird daher zusätzlich eine
    Kopfprinzip-Grundlage angelegt (nicht Standard); ist die Standard-Grundlage
    ohnehin schon das Kopfprinzip, genügt diese eine.
    """
    if ev.stimmprinzip == 'verteilerschluessel':
        vs = ev.stimm_verteilerschluessel
        standard = EVStimmgrundlage.objects.create(
            ev=ev, verteilerschluessel=vs, ist_kopfprinzip=False,
            wirtschaftsjahr=ev.stimm_wirtschaftsjahr, ist_standard=True,
            bezeichnung_anzeige=_bezeichnung(
                ist_kopfprinzip=False, verteilerschluessel=vs,
            ),
        )
        _erzeuge_kopfprinzip(ev, ist_standard=False)
        return standard
    return _erzeuge_kopfprinzip(ev, ist_standard=True)


@transaction.atomic
def hinzufuegen(ev, *, verteilerschluessel=None, ist_kopfprinzip=False,
               wirtschaftsjahr=0, ist_standard=False) -> EVStimmgrundlage:
    """Ergänzt der EV eine weitere Stimmgrundlage (Mehrfachauswahl, Kap. 2).

    Nur VOR dem Einladungsversand möglich — danach sind Stimmgrundlagen wie
    die Tagesordnung selbst festgeschrieben (§ 23 Abs. 2 WEG entsprechend,
    spätestens ab Checkout ohnehin gesperrt).
    """
    from apps.versammlung.services import ev_service

    if ev.status in ev_service.STATI_NACH_VERSAND:
        raise ValidationError(
            'Stimmgrundlagen können nach dem Einladungsversand nicht mehr '
            f'ergänzt werden (Status "{ev.get_status_display()}").'
        )
    if bool(verteilerschluessel) == bool(ist_kopfprinzip):
        raise ValidationError(
            'Entweder ein Verteilerschlüssel oder das echte Kopfprinzip ist '
            'anzugeben — nie beides, nie keines.'
        )
    if verteilerschluessel is not None:
        if verteilerschluessel.objekt_id != ev.objekt_id:
            raise ValidationError(
                'Der Verteilerschlüssel gehört zu einem anderen Objekt.'
            )
        if verteilerschluessel.vs_typ == 'verbrauch':
            raise ValidationError(
                'Ein Verbrauchsschlüssel ist keine zulässige Stimmgrundlage — '
                'Verbrauch ist kein Stimmrecht nach irgendeiner Teilungserklärung.'
            )

    if ist_standard:
        ev.stimmgrundlagen.filter(ist_standard=True).update(ist_standard=False)

    grundlage = EVStimmgrundlage(
        ev=ev, verteilerschluessel=verteilerschluessel,
        ist_kopfprinzip=ist_kopfprinzip, wirtschaftsjahr=wirtschaftsjahr,
        ist_standard=ist_standard,
        bezeichnung_anzeige=_bezeichnung(
            ist_kopfprinzip=ist_kopfprinzip, verteilerschluessel=verteilerschluessel,
        ),
    )
    grundlage.full_clean()
    grundlage.save()
    return grundlage
