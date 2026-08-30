"""
Stufe-2-Freigabe Rechnungseingang — Umbau v1.1 (Spec Kap. 5.2).

Die Freigabe-Berechtigung ergibt sich AUSSCHLIESSLICH aus dem
objektbasierten `Objekt.zahlungsfreigabe_grenzen` (Rolle + Betragsschwelle)
über die bestehenden v1.2-Funktionen `_ermittle_freigabestufe` /
`_ermittle_freigabeperson`. Das persönliche `freigabe_limit` aus v1.0
wurde ersatzlos entfernt (Spec v1.1 Kap. 0 #2).

Rollen-Auflösung (dokumentierte Annahme, an reale Strukturen angepasst):
- Reale Grenzen-Struktur ist die flache Liste
  [{bis, rolle, frist_tage, beschreibung}] (V8-Abweichung zur Spec).
- 'auto'-Stufe: B1-Default — auch Bagatellen laufen durch Stufe 2;
  zuständig ist die nächste manuelle Stufe.
- 'sachbearbeiter'/'objektmanager': Objektbetreuer (+ Vertretung),
  per MitarbeiterObjektZuordnung (aufgabe='objektmanagement') dem Objekt
  zugeordnete Mitarbeiter, oder Gruppe 'Objektmanager'/'Sachbearbeiter'.
- 'geschaeftsfuehrer': Abteilung 'geschaeftsfuehrer', Gruppe
  'Geschaeftsfuehrer' oder Superuser. GF darf jede Stufe freigeben
  (Eskalationsziel laut Grenzen-Konfig).
"""
from ..recognition import (
    _ermittle_freigabestufe,
    _ermittle_freigabeperson,
    _lade_grenzen,
    _naechste_manuelle_stufe,
)


def _ist_geschaeftsfuehrer(user) -> bool:
    if user.is_superuser:
        return True
    if user.groups.filter(name='Geschaeftsfuehrer').exists():
        return True
    profil = getattr(user, 'mitarbeiter_profil', None)
    return bool(profil and 'geschaeftsfuehrer' in (profil.abteilungen or []))


def _ist_objekt_freigeber(user, objekt) -> bool:
    """Sachbearbeiter-/Objektmanager-Stufe: dem Objekt zugeordnete Bearbeiter."""
    if objekt is None:
        return False
    if objekt.betreuer_id == user.id or objekt.betreuer_vertretung_id == user.id:
        return True
    profil = getattr(user, 'mitarbeiter_profil', None)
    if profil and profil.objekt_zuordnungen.filter(
        objekt=objekt, aufgabe='objektmanagement',
    ).exists():
        return True
    return user.groups.filter(name__in=['Objektmanager', 'Sachbearbeiter']).exists()


def freigabestufe_fuer(rechnung) -> dict:
    """Zuständige (manuelle) Freigabestufe laut zahlungsfreigabe_grenzen.
    'auto'-Stufe → nächste manuelle Stufe (B1: alles durch Stufe 2)."""
    grenzen = _lade_grenzen(rechnung)
    stufe = _ermittle_freigabestufe(rechnung.betrag_brutto or 0, grenzen)
    if stufe.get('rolle') == 'auto':
        stufe = _naechste_manuelle_stufe(grenzen)
    return stufe


def darf_freigeben(rechnung, user) -> bool:
    """Objektbasierte Stufe-2-Berechtigung (Spec 5.2). Kein persönliches Limit."""
    if rechnung.betrag_brutto is None:
        return False
    if _ist_geschaeftsfuehrer(user):
        return True
    rolle = freigabestufe_fuer(rechnung).get('rolle', '')
    if rolle in ('sachbearbeiter', 'objektmanager'):
        return _ist_objekt_freigeber(user, rechnung.objekt if rechnung.objekt_id else None)
    return False   # 'geschaeftsfuehrer'-Stufe: oben bereits behandelt


def _hat_offene_wkz_vorlage(rechnung) -> bool:
    """True, wenn zu der Rechnung eine WKZ-Vorlage besteht, die die Zahlung
    übernimmt (jede Vorlage außer 'beendet')."""
    return rechnung.wkz_vorlagen.exclude(status='beendet').exists()


def route_zur_freigabe(rechnung, geprueft_von=None):
    """Stufe-1-Abschluss „Geprüft → zur Freigabe" (Spec 5.1):
    Status → zur_freigabe, Freigabestufe/-person über die bestehenden
    v1.2-Funktionen ermitteln und zuweisen.

    Lernlogik (Entscheidung Patrik 2026-07-14, ersetzt B6-Default „nein"):
    Beim Übergang zur Freigabe wird die Match-Regel aus der von der
    Buchhaltung geprüften/bestätigten Kontierung erstellt bzw. bestätigt
    (gleiches Konto → trefferzahl++). Der Stufe-2-Freigeber ändert die
    Regel nur bei bewusster Konto-Korrektur mit Rückfrage (Spec 5.3).

    Sonderfall WKZ: Besteht zu der Rechnung eine (nicht beendete) WKZ-Vorlage,
    läuft die Zahlung über die wiederkehrende Zahlung — mit eigener Freigabe
    unter „Rechnungsfreigabe". Die Rechnung verlässt deshalb JETZT, mit dem
    Abschluss der Erfassung, den normalen Zahlweg (status='wkz_beleg') und
    nicht schon beim Anlegen der Vorlage."""
    if _hat_offene_wkz_vorlage(rechnung):
        from apps.buchhaltung.services.wkz.vorlage_service import uebergib_rechnung_an_wkz
        return uebergib_rechnung_an_wkz(rechnung, user=geprueft_von)

    if geprueft_von is not None:
        from ..recognition import lege_match_regel_an
        regel = lege_match_regel_an(rechnung, geprueft_von, 'pruefung', lernen=True)
        if regel:
            rechnung.match_regel = regel
    stufe = freigabestufe_fuer(rechnung)
    rechnung.status = 'zur_freigabe'
    rechnung.zugewiesen_an = _ermittle_freigabeperson(rechnung, stufe)
    rechnung.save(update_fields=['status', 'zugewiesen_an', 'match_regel'])
    return rechnung
