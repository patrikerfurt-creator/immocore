"""
Einladungs-Service (Spec v1.1 Kap. 6–8) — Einladungs-PDF, Versandplan und
Multi-Kanal-Versand.

Drei Grundsätze aus der Spec, die hier durchgängig durchgehalten sind:

1. **Ein Dokument je EV, nicht je Person.** Die Owner-Regel B-Hybrid am
   ``Dokument`` erlaubt höchstens einen Kontext-FK — das Einladungs-PDF hängt
   deshalb am ``objekt``, der Personenbezug steht im ``EVVersandprotokoll``
   (Spec Kap. 8.2).
2. **Kein stiller Versand.** Ist nur ein Konsolen-/Dummy-Mailbackend
   konfiguriert, gilt der Versand als fehlgeschlagen statt als erledigt —
   sonst wäre eine EV "eingeladen", ohne dass eine Mail das Haus verlassen hat
   (dieselbe Falle wie bei den Handwerkeraufträgen, Commit 3fb630d).
3. **Keine stille Auslassung.** Nicht-PDF-Anlagen, fehlende Adressen und
   fehlende Termine führen zu klaren Meldungen, nicht zu einem stillschweigend
   unvollständigen Ergebnis.
"""
import csv
import io
import logging
from datetime import timedelta
from pathlib import Path

import weasyprint
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from apps.dokumente.models import Dokument
from apps.dokumente.services import beleg_service
from apps.versammlung.models import EVVersandprotokoll
from apps.versammlung.services import ev_service

logger = logging.getLogger(__name__)

# Ladungsfrist § 24 Abs. 4 WEG — Unterschreitung macht Beschlüsse anfechtbar,
# nicht nichtig; deshalb Warnung statt Sperre.
LADUNGSFRIST_TAGE = 21

# Backends, die nie tatsächlich versenden. Zwilling zu
# ``apps.handwerker.tasks._NICHT_VERSANDFAEHIGE_BACKENDS`` — bewusst dupliziert
# statt eine private Funktion einer fremden App zu importieren. Sobald ein
# dritter Aufrufer dazukommt, gehört die Prüfung in einen gemeinsamen Helfer.
_NICHT_VERSANDFAEHIGE_BACKENDS = (
    'django.core.mail.backends.console.EmailBackend',
    'django.core.mail.backends.dummy.EmailBackend',
)

EPOST_UNTERORDNER = 'epost'


def versand_konfiguriert() -> bool:
    """Prüft, ob ``settings.EMAIL_BACKEND`` tatsächlich versendet.

    ``locmem`` (Django-Tests) gilt bewusst als versandfähig.
    """
    backend = settings.EMAIL_BACKEND
    if backend in _NICHT_VERSANDFAEHIGE_BACKENDS:
        return False
    if backend == 'django.core.mail.backends.smtp.EmailBackend' and not settings.EMAIL_HOST:
        return False
    return True


def _erste_email(person) -> str:
    """Erste brauchbare E-Mail-Adresse einer Person.

    ``Person.emails`` (JSON-Liste) ist das neue Feld, ``Person.email`` das
    Legacy-Feld — beide sind im Bestand gefüllt, deshalb wird in dieser
    Reihenfolge gesucht. Einträge der JSON-Liste können Strings oder Dicts
    (``{"adresse": …}`` / ``{"email": …}``) sein.
    """
    for eintrag in (person.emails or []):
        if isinstance(eintrag, str) and eintrag.strip():
            return eintrag.strip()
        if isinstance(eintrag, dict):
            for schluessel in ('adresse', 'email', 'wert'):
                wert = (eintrag.get(schluessel) or '').strip()
                if wert:
                    return wert
    return (person.email or '').strip()


def _hat_portalzugang(person) -> bool:
    """Portalzugang der Person.

    Gibt bis zum Abschluss des Voraussetzungsmoduls "Eigentümer-Portal"
    (Spec Kap. 11) immer ``False`` zurück — im Code existiert kein
    ``PortalZugang``, ``Person`` hat keinen User-Bezug. Der Kanal ``portal``
    ist damit vorbereitet, aber nie das Ergebnis der Kanalermittlung.
    """
    return False


def pruefe_ladungsfrist(ev) -> dict:
    """Ladungsfrist-Prüfung (§ 24 Abs. 4 WEG) — informativ, nie blockierend."""
    if not ev.termin:
        return {
            'termin': None, 'tage_bis_termin': None, 'frist_tage': LADUNGSFRIST_TAGE,
            'eingehalten': False,
            'warnung': 'Kein Termin gesetzt — die Ladungsfrist ist nicht prüfbar.',
        }

    tage = (ev.termin - timezone.now()).days
    eingehalten = tage >= LADUNGSFRIST_TAGE
    warnung = ''
    if not eingehalten:
        warnung = (
            f'Die Ladungsfrist von {LADUNGSFRIST_TAGE} Tagen (§ 24 Abs. 4 WEG) '
            f'ist unterschritten — bis zum Termin sind es noch {tage} Tage. '
            'Beschlüsse dieser Versammlung sind dadurch anfechtbar.'
        )
    return {
        'termin': ev.termin, 'tage_bis_termin': tage,
        'frist_tage': LADUNGSFRIST_TAGE, 'eingehalten': eingehalten,
        'warnung': warnung,
    }


def _anlagen_pruefen(anlagen_ids) -> list:
    """Lädt die Anlagen-Dokumente und stellt sicher, dass alles PDF ist."""
    if not anlagen_ids:
        return []

    dokumente = list(Dokument.objects.filter(id__in=anlagen_ids))
    gefunden = {str(d.id) for d in dokumente}
    fehlend = [str(a) for a in anlagen_ids if str(a) not in gefunden]
    if fehlend:
        raise ValidationError(
            'Anlage nicht gefunden: ' + ', '.join(fehlend)
        )

    keine_pdf = [d.dateiname for d in dokumente
                 if not d.dateiname.lower().endswith('.pdf')]
    if keine_pdf:
        raise ValidationError(
            'Nur PDF-Anlagen können an die Einladung angehängt werden — '
            'nicht möglich: ' + ', '.join(keine_pdf)
        )
    # Reihenfolge der Übergabe beibehalten, nicht die DB-Reihenfolge.
    nach_id = {str(d.id): d for d in dokumente}
    return [nach_id[str(a)] for a in anlagen_ids]


def _haenge_anlagen_an(pdf_bytes: bytes, anlagen: list) -> bytes:
    """Hängt PDF-Anlagen an das gerenderte PDF an (PyMuPDF).

    WeasyPrint kann bestehende PDFs nicht zusammenführen. Fehlt ``fitz`` im
    Image (auf dem Prod-Image schon vorgekommen), bricht die Erzeugung mit
    Betriebshinweis ab — die Anlage wird NICHT stillschweigend weggelassen.
    """
    if not anlagen:
        return pdf_bytes

    try:
        import fitz
    except ImportError as fehler:
        raise ValidationError(
            'PDF-Anlagen können nicht angehängt werden: PyMuPDF (fitz) ist in '
            'diesem Container nicht installiert. Entweder das Image mit '
            'PyMuPDF bauen oder die Einladung ohne Anlagen erzeugen und die '
            'Anlagen separat versenden.'
        ) from fehler

    ziel = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        for dokument in anlagen:
            pfad = beleg_service.dokument_pfad(dokument)
            if not Path(pfad).exists():
                raise ValidationError(
                    f'Datei der Anlage "{dokument.dateiname}" fehlt auf der '
                    f'Ablage ({pfad}).'
                )
            with fitz.open(str(pfad)) as anlage:
                ziel.insert_pdf(anlage)
        return ziel.tobytes()
    finally:
        ziel.close()


def rendere_einladung(ev, *, empfaenger=None, anlagen=None) -> bytes:
    """Rendert das Einladungs-PDF (ohne Persistierung).

    ``empfaenger`` (``EVTeilnehmer``) erzeugt die personalisierte Fassung für
    den Postversand — mit Anschrift und Briefanrede. Ohne Empfänger entsteht
    die neutrale Fassung, die im DMS liegt und per Portal/Mail geht.
    """
    kontext = {
        'ev': ev,
        'objekt': ev.objekt,
        'tagesordnung': list(ev.tagesordnung.order_by('nummer')),
        'ladungsfrist': pruefe_ladungsfrist(ev),
        'empfaenger': empfaenger,
        'person': empfaenger.person if empfaenger else None,
        'anlagen': anlagen or [],
        'erstellt_am': timezone.now(),
    }
    html = render_to_string('versammlung/einladung.html', kontext)
    return weasyprint.HTML(string=html).write_pdf()


@transaction.atomic
def erzeuge_einladungs_pdf(ev, erstellt_von, anlagen_ids=None) -> Dokument:
    """Erzeugt das Einladungs-PDF und legt es als DMS-Dokument am Objekt ab.

    Ein bereits vorhandenes Einladungs-PDF wird NICHT gelöscht (GoBD) —
    ``ev.einladungs_pdf`` zeigt danach auf die neue Fassung, die alte bleibt
    als Dokument am Objekt bestehen.
    """
    if not ev.termin or not ev.ort.strip():
        raise ValidationError(
            'Für die Einladung müssen Termin und Ort feststehen (Task 1).'
        )
    if not ev.tagesordnung.exists():
        raise ValidationError(
            'Für die Einladung muss die Tagesordnung mindestens einen Punkt '
            'enthalten (Task 2).'
        )

    anlagen = _anlagen_pruefen(anlagen_ids)
    pdf_bytes = _haenge_anlagen_an(rendere_einladung(ev, anlagen=anlagen), anlagen)

    dateiname = f'Einladung_EV_{ev.termin:%Y-%m-%d}.pdf'
    dokument = Dokument.objects.create(
        datei=ContentFile(pdf_bytes, name=dateiname),
        dateiname=dateiname,
        kategorie='EV-Einladung',
        dokument_typ='korrespondenz',
        beschreibung=(
            f'Einladung zur Eigentümerversammlung am '
            f'{ev.termin:%d.%m.%Y} — {ev.objekt.bezeichnung}'
        ),
        # Owner-Regel B-Hybrid: ausschließlich objekt, nie zusätzlich person.
        objekt=ev.objekt,
        hochgeladen_von=erstellt_von,
    )

    ev.einladungs_pdf = dokument
    ev.save(update_fields=['einladungs_pdf'])
    ev_service.vermerke_ereignis(
        ev, 'einladung_erzeugt', erstellt_von,
        text=(
            f'Einladungs-PDF erzeugt ({len(anlagen)} Anlage(n), '
            f'{ev.tagesordnung.count()} TOP).'
        ),
        neuer_wert=dateiname,
    )
    return dokument


def versandplan(ev) -> dict:
    """Ermittelt je Teilnehmer den vorgeschlagenen Versandkanal (Spec Kap. 8.1).

    Der Plan ist ein Vorschlag — die Verwaltung darf jeden Kanal überschreiben.
    Teilnehmer ohne Stimmkraft (Eigentümerwechsel nach Ladung) werden
    mitgeliefert, aber als ``nicht_stimmberechtigt`` markiert.
    """
    eintraege = []
    for teilnehmer in ev.teilnehmer.select_related('person').all():
        person = teilnehmer.person
        email = _erste_email(person)
        portal = _hat_portalzugang(person)

        if portal and email:
            kanal, hinweis = 'portal', ''
        elif email:
            kanal, hinweis = 'email', ''
        else:
            kanal = 'epost'
            hinweis = 'Keine E-Mail-Adresse hinterlegt — Postversand.'
            if not (person.adresse or '').strip():
                hinweis = (
                    'Weder E-Mail-Adresse noch Anschrift hinterlegt — die '
                    'Einladung kann nicht zugestellt werden.'
                )

        eintraege.append({
            'teilnehmer_id': str(teilnehmer.id),
            'person_id': str(person.id),
            'name': person.name,
            'kanal': kanal,
            'empfaenger': email or (person.adresse or '').replace('\n', ', '),
            'hat_email': bool(email),
            'hat_portalzugang': portal,
            'stimmkraft': teilnehmer.stimmkraft,
            'nicht_stimmberechtigt': teilnehmer.stimmkraft == 0,
            'hinweis': hinweis,
        })

    eintraege.sort(key=lambda e: e['name'])
    zusammenfassung = {kanal: 0 for kanal in ('portal', 'email', 'epost')}
    for eintrag in eintraege:
        zusammenfassung[eintrag['kanal']] += 1

    return {
        'ev_id': str(ev.id),
        'eintraege': eintraege,
        'zusammenfassung': zusammenfassung,
        'anzahl': len(eintraege),
        'ladungsfrist': pruefe_ladungsfrist(ev),
        'portal_verfuegbar': False,
        'portal_hinweis': (
            'Der Kanal "Portal" ist erst nutzbar, wenn das Modul '
            'Eigentümer-Portal umgesetzt ist (Spec Kap. 11). Bis dahin werden '
            'alle Eigentümer per E-Mail oder EPost geladen.'
        ),
    }


def epost_verzeichnis(ev) -> Path:
    """Zielordner für den Postversand — immer unterhalb von ``MEDIA_ROOT``.

    Pfade sind damit Container-Pfade (``/app/media/epost/…``) und nie
    Host-/Windows-Pfade.
    """
    datum = ev.termin.strftime('%Y-%m-%d') if ev.termin else 'ohne-termin'
    return Path(settings.MEDIA_ROOT) / EPOST_UNTERORDNER / f'EV_{ev.id}_{datum}'


def _schreibe_epost(ev, teilnehmer, ordner: Path) -> Path:
    """Schreibt die personalisierte PDF für einen Postempfänger."""
    person = teilnehmer.person
    pdf_bytes = rendere_einladung(ev, empfaenger=teilnehmer)
    name = slugify(f'{person.nachname}-{person.vorname}') or slugify(person.name) or 'empfaenger'
    pfad = ordner / f'{name}_Einladung.pdf'
    pfad.write_bytes(pdf_bytes)
    return pfad


def _schreibe_epost_csv(ordner: Path, zeilen: list) -> Path:
    """Begleitliste für den Postversand.

    Semikolon-getrennt und UTF-8 **mit BOM** — so öffnet Excel die Datei ohne
    Import-Dialog und mit korrekten Umlauten.
    """
    puffer = io.StringIO()
    writer = csv.writer(puffer, delimiter=';', lineterminator='\r\n')
    writer.writerow(['Name', 'Anschrift', 'Einheiten', 'PDF-Datei'])
    for zeile in zeilen:
        writer.writerow(zeile)

    pfad = ordner / 'versand.csv'
    pfad.write_text(puffer.getvalue(), encoding='utf-8-sig')
    return pfad


def _versende_mail(ev, teilnehmer, adresse: str, pdf_bytes: bytes, dateiname: str) -> None:
    kontext = {
        'ev': ev, 'objekt': ev.objekt,
        'person': teilnehmer.person,
        'tagesordnung': list(ev.tagesordnung.order_by('nummer')),
        'ladungsfrist': pruefe_ladungsfrist(ev),
    }
    text_body = render_to_string('email/ev_einladung.txt', kontext)
    html_body = render_to_string('email/ev_einladung.html', kontext)

    mail = EmailMultiAlternatives(
        subject=(
            f'Einladung zur Eigentümerversammlung '
            f'{ev.objekt.bezeichnung} am {ev.termin:%d.%m.%Y}'
        ),
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[adresse],
    )
    mail.attach_alternative(html_body, 'text/html')
    mail.attach(dateiname, pdf_bytes, 'application/pdf')
    mail.send()


def versende_einladungen(ev, versendet_von, plan: dict = None) -> dict:
    """Versendet die Einladungen über die gewählten Kanäle (Spec Kap. 8).

    ``plan``: ``{teilnehmer_id: kanal}`` — überschreibt den Vorschlag aus
    ``versandplan()``. Nicht genannte Teilnehmer bekommen den Vorschlagskanal.

    Bewusst NICHT in einer Transaktion um den ganzen Lauf: ein Mailfehler beim
    zwanzigsten Empfänger darf die neunzehn erfolgreichen Protokollzeilen nicht
    zurückrollen — sonst wäre nach einem Teilfehler nicht mehr feststellbar,
    wer die Einladung schon hat. Jede Protokollzeile wird einzeln geschrieben.

    Rückgabe: ``{'gesamt', 'erfolgreich', 'fehlgeschlagen', 'uebersprungen',
    'kanaele', 'epost_ordner', 'fehler'}``.
    """
    if ev.einladungs_pdf_id is None:
        raise ValidationError(
            'Es gibt noch kein Einladungs-PDF — bitte zuerst erzeugen.'
        )

    vorschlag = versandplan(ev)
    gewuenscht = {str(k): v for k, v in (plan or {}).items()}
    erlaubte_kanaele = {'portal', 'email', 'epost'}
    unbekannt = set(gewuenscht.values()) - erlaubte_kanaele
    if unbekannt:
        raise ValidationError('Unbekannter Versandkanal: ' + ', '.join(sorted(unbekannt)))

    mail_moeglich = versand_konfiguriert()
    pdf_bytes = beleg_service.dokument_pfad(ev.einladungs_pdf).read_bytes()
    dateiname = ev.einladungs_pdf.dateiname

    teilnehmer_nach_id = {
        str(t.id): t for t in ev.teilnehmer.select_related('person').all()
    }
    epost_ordner = None
    epost_zeilen = []
    ergebnis = {
        'gesamt': 0, 'erfolgreich': 0, 'fehlgeschlagen': 0, 'uebersprungen': 0,
        'kanaele': {'portal': 0, 'email': 0, 'epost': 0},
        'epost_ordner': '', 'fehler': [],
    }

    for eintrag in vorschlag['eintraege']:
        teilnehmer = teilnehmer_nach_id[eintrag['teilnehmer_id']]
        person = teilnehmer.person
        kanal = gewuenscht.get(eintrag['teilnehmer_id'], eintrag['kanal'])
        ergebnis['gesamt'] += 1

        status = 'erfolgreich'
        fehlertext = ''
        empfaenger = eintrag['empfaenger']
        epost_pfad = ''

        try:
            if kanal == 'portal':
                # Ohne Portalmodul gibt es keinen Zustellweg — nicht als
                # Erfolg verbuchen, sonst gilt der Eigentümer als geladen.
                status = 'uebersprungen'
                fehlertext = (
                    'Kanal "Portal" ist noch nicht verfügbar (Modul '
                    'Eigentümer-Portal, Spec Kap. 11).'
                )
            elif kanal == 'email':
                if not eintrag['hat_email']:
                    status = 'uebersprungen'
                    fehlertext = 'Keine E-Mail-Adresse hinterlegt.'
                elif not mail_moeglich:
                    status = 'fehlgeschlagen'
                    fehlertext = (
                        'E-Mail-Versand ist auf diesem Server nicht '
                        f'konfiguriert (EMAIL_BACKEND={settings.EMAIL_BACKEND!r}) '
                        '— es wurde nichts versendet.'
                    )
                else:
                    _versende_mail(ev, teilnehmer, empfaenger, pdf_bytes, dateiname)
            elif kanal == 'epost':
                if not (person.adresse or '').strip():
                    status = 'uebersprungen'
                    fehlertext = 'Keine Anschrift hinterlegt — Postversand nicht möglich.'
                else:
                    if epost_ordner is None:
                        epost_ordner = epost_verzeichnis(ev)
                        epost_ordner.mkdir(parents=True, exist_ok=True)
                    pfad = _schreibe_epost(ev, teilnehmer, epost_ordner)
                    epost_pfad = str(pfad)
                    empfaenger = (person.adresse or '').replace('\n', ', ')
                    epost_zeilen.append([
                        person.name, empfaenger,
                        ', '.join(teilnehmer.anteile.values_list(
                            'einheit_nr_snapshot', flat=True)),
                        pfad.name,
                    ])
        except Exception as fehler:            # noqa: BLE001 — s. Docstring
            logger.exception(
                'EV-Versand an %s (%s) fehlgeschlagen.', person.name, kanal,
            )
            status = 'fehlgeschlagen'
            fehlertext = str(fehler)

        EVVersandprotokoll.objects.create(
            ev=ev, person=person, kanal=kanal, status=status,
            empfaenger=empfaenger[:255], epost_pfad=epost_pfad[:500],
            fehlertext=fehlertext, versendet_von=versendet_von,
        )

        if status == 'erfolgreich':
            ergebnis['erfolgreich'] += 1
            ergebnis['kanaele'][kanal] += 1
        else:
            ergebnis[status] += 1
            ergebnis['fehler'].append({
                'name': person.name, 'kanal': kanal,
                'status': status, 'text': fehlertext,
            })

    if epost_ordner is not None:
        _schreibe_epost_csv(epost_ordner, epost_zeilen)
        ergebnis['epost_ordner'] = str(epost_ordner)

    ev_service.vermerke_ereignis(
        ev, 'einladung_versendet', versendet_von,
        text=(
            f'Versand abgeschlossen: {ergebnis["erfolgreich"]} von '
            f'{ergebnis["gesamt"]} erfolgreich '
            f'(E-Mail {ergebnis["kanaele"]["email"]}, '
            f'EPost {ergebnis["kanaele"]["epost"]}), '
            f'{ergebnis["fehlgeschlagen"]} fehlgeschlagen, '
            f'{ergebnis["uebersprungen"]} übersprungen.'
        ),
    )
    if ergebnis['fehlgeschlagen'] or ergebnis['uebersprungen']:
        ev_service.vermerke_ereignis(
            ev, 'versand_fehler', versendet_von,
            text='; '.join(
                f'{f["name"]} ({f["kanal"]}): {f["text"]}'
                for f in ergebnis['fehler']
            )[:4000],
        )

    # Status nur weiterschalten, wenn wenigstens eine Einladung heraus ist.
    if ergebnis['erfolgreich'] and ev.status in ('entwurf', 'in_bearbeitung'):
        if ev.status == 'entwurf':
            ev_service.wechsle_status(ev, 'in_bearbeitung', versendet_von)
        ev_service.wechsle_status(
            ev, 'einladungen_versendet', versendet_von,
            text='Einladungen versendet.',
        )

    return ergebnis
