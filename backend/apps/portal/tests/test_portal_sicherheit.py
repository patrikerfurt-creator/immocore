"""
Adversariale Abnahme der fünf neuen Portal-Endpunkte (Spec Portal-Erweiterung
v1.1, Kap. 9.5 und 11): Vorgang-Typen, Vorgänge (Liste/Detail/Anlage),
Personenkonto-Saldo und Fälligkeiten.

Ziel dieser Datei ist NICHT, die Endpunkte schön zu finden, sondern zu
versuchen, sie zu brechen — ergänzend zu ``test_vorgaenge.py``/
``test_konto.py`` (Grundfunktion) und zur Isolations-Stichprobe in
``test_einheiten_und_isolation.py`` (fremde IDs quer über alle Endpunkte).

Deckt ab (Nummerierung nach Auftrag):
  2.  Keine Sitzung / Mitarbeiter-JWT auf allen fünf Endpunkten.
  3.  Gesperrter Zugang / abgelaufene Sitzung auf allen fünf Endpunkten.
  4.  Rate-Limit ``portal_vorgang_erstellen`` (20/Tag, je Portal-Identität),
      GET auf derselben View bleibt ungethrottelt.
  5.  Schema-Test „keine internen Felder" — rekursiv, über alle fünf
      Endpunkte.
  6.  Interne Ereignisse und KI-Antwortvorschläge tauchen in keiner
      Portal-Antwort auf (mit tatsächlich angelegten Datensätzen, nicht nur
      einer Schlüsselprüfung ins Leere).
  7.  Sichtbarkeitsregel-Härtung: ``portal_sichtbar=False`` ist auch über
      die Detail-Route nie erreichbar.
  8.  Anlage-Härtung: Body-Injection auf feste Felder (``quelle``,
      ``status``, ``portal_sichtbar``, ``erstellt_von``).
  9.  Fälligkeiten-Pagination bei mehr als ``page_size`` Posten.
"""
import json
import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.buchhaltung.models import HausgeldSollstellung
from apps.portal.services import zugang_service
from apps.vorgaenge.models import Vorgang, VorgangAntwortVorschlag, VorgangTyp
from apps.vorgaenge.services import vorgang_service

from .basis import (
    erstelle_eigentuemer,
    erstelle_einheit,
    erstelle_objekt,
    verknuepfe,
)

User = get_user_model()

VORGANG_TYPEN_URL = '/api/v1/portal/vorgang-typen/'
VORGAENGE_URL = '/api/v1/portal/vorgaenge/'
SALDO_URL = '/api/v1/portal/personenkonto/saldo/'
FAELLIGKEITEN_URL = '/api/v1/portal/faelligkeiten/'


def _detail_url(vorgang_id):
    return f'/api/v1/portal/vorgaenge/{vorgang_id}/'


def _mitarbeiter(username='sicherheit-tester'):
    return User.objects.create_user(username=username, password='x')


def _typ(code='sicherheit-typ', **kwargs):
    kwargs.setdefault('portal_erstellbar', True)
    kwargs.setdefault('aktiv', True)
    return VorgangTyp.objects.create(code=code, bezeichnung='Mängelmeldung', **kwargs)


def _alle_schluessel(daten) -> set:
    """Sammelt rekursiv ALLE Dict-Schlüssel einer (verschachtelten)
    JSON-artigen Struktur — Grundlage des Schema-Tests „keine internen
    Felder", der beim Hinzufügen eines neuen Felds an JEDER Verschachtelungs-
    tiefe wieder anspringt."""
    schluessel = set()

    def _walk(wert):
        if isinstance(wert, dict):
            for k, v in wert.items():
                schluessel.add(k)
                _walk(v)
        elif isinstance(wert, (list, tuple)):
            for eintrag in wert:
                _walk(eintrag)

    _walk(daten)
    return schluessel


# Kap. 9.5 Test 5: verbotene Schlüssel über BEIDE Response-Familien hinweg.
# Keine Überschneidung mit den laut Spec erlaubten Vertragsfeldern — die
# Vereinigung kann deshalb gefahrlos gegen jede der fünf Antworten geprüft
# werden.
VERBOTENE_SCHLUESSEL = {
    # Vorgänge
    'zugewiesen_an', 'wiedervorlage_am', 'mail_referenz', 'telefon_rufnummer',
    'erstellt_von', 'geschlossen_von', 'geschlossen_am', 'status_anzeige',
    'prioritaet', 'quelle', 'portal_sichtbar', 'antwort_vorschlaege',
    # Fälligkeiten/Saldo
    'mahnstufe', 'mahnkarenz_bis', 'korrektur_grund', 'korrektur_vorgang_id',
    'nachhol_aus_wp_id', 'opos_nr', 'status_cached', 'storniert_am',
    'storniert_grund', 'sollstellungslauf', 'ist_betrag',
}


def _fuenf_endpunkte(vorgang_id):
    """Tabelle (name, method, url) der fünf Endpunkte für Stichproben, die
    für ALLE gleich ablaufen (kein Sitzungszugriff, gesperrter Zugang,
    abgelaufene Sitzung). ``vorgang_id`` wird für die Detail-Route gebraucht
    — im negativen Auth-Fall ist ihr Inhalt irrelevant, die Anfrage scheitert
    schon an der Authentifizierung."""
    return [
        ('vorgang-typen', 'get', VORGANG_TYPEN_URL, None),
        ('vorgaenge-liste', 'get', VORGAENGE_URL, None),
        ('vorgaenge-anlage', 'post', VORGAENGE_URL, {'typ_id': str(uuid.uuid4()), 'betreff': 'x', 'einheit_id': str(uuid.uuid4())}),
        ('vorgang-detail', 'get', _detail_url(vorgang_id), None),
        ('saldo', 'get', SALDO_URL, None),
        ('faelligkeiten', 'get', FAELLIGKEITEN_URL, None),
    ]


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalOhneSitzungTest(APITestCase):
    """Test 2 (Teil 1): kein Authorization-Header auf allen fünf Endpunkten."""

    def setUp(self):
        cache.clear()

    def test_alle_fuenf_endpunkte_ohne_header_liefern_401(self):
        for name, methode, url, daten in _fuenf_endpunkte(uuid.uuid4()):
            with self.subTest(endpunkt=name):
                aufruf = getattr(self.client, methode)
                response = aufruf(url, daten, format='json') if daten else aufruf(url)
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED,
                    f'{name}: erwartet 401, bekam {response.status_code}',
                )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalMitarbeiterJwtTest(APITestCase):
    """Test 2 (Teil 2): ein internes Mitarbeiter-JWT darf die Portal-
    Endpunkte NICHT erreichen — weder als ``Bearer``-Token (fällt schon am
    Schema-Präfix durch) noch als vorgetäuschtes ``Portal``-Token (ein JWT
    ist keine gültige ``PortalSession.token``)."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('jwt-tester')
        self.jwt = str(RefreshToken.for_user(self.mitarbeiter).access_token)

    def test_bearer_praefix_wird_von_portal_auth_nicht_angenommen(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.jwt}')
        for name, methode, url, daten in _fuenf_endpunkte(uuid.uuid4()):
            with self.subTest(endpunkt=name):
                aufruf = getattr(self.client, methode)
                response = aufruf(url, daten, format='json') if daten else aufruf(url)
                self.assertIn(
                    response.status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                    f'{name}: erwartet 401/403, bekam {response.status_code}',
                )

    def test_jwt_als_portal_token_gespiegelt_wird_abgewiesen(self):
        """Selbst mit dem korrekten Schema-Präfix ``Portal`` ist ein
        JWT-String keine in ``PortalSession`` existierende Sitzung."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.jwt}')
        for name, methode, url, daten in _fuenf_endpunkte(uuid.uuid4()):
            with self.subTest(endpunkt=name):
                aufruf = getattr(self.client, methode)
                response = aufruf(url, daten, format='json') if daten else aufruf(url)
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED,
                    f'{name}: erwartet 401, bekam {response.status_code}',
                )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalGesperrtUndAbgelaufenTest(APITestCase):
    """Test 3: ein zwischenzeitlich gesperrter Zugang und eine abgelaufene
    Sitzung wirken SOFORT auf allen fünf Endpunkten — nicht erst nach
    erneutem Login."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('sperr-tester')
        self.person = erstelle_eigentuemer(personennummer='P-SPERR-1', email='sperr@example.org')
        self.weg = erstelle_objekt('SPERR-A', 'WEG Sperrweg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        verknuepfe(self.person, self.einheit)

        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=_typ('sperr-typ'), betreff='Vorgang vor Sperrung',
            erstellt_von=self.mitarbeiter, objekt=self.weg, einheit=self.einheit,
            portal_sichtbar=True,
        )

        self.zugang, token = zugang_service.lade_ein(self.person)
        self.session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session.token}')

    def test_gesperrter_zugang_wirkt_sofort_auf_allen_endpunkten(self):
        # Sitzung ist zu diesem Zeitpunkt bereits ausgestellt — die Sperre
        # trifft eine BESTEHENDE Sitzung, kein Login-Versuch danach.
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])

        for name, methode, url, daten in _fuenf_endpunkte(self.vorgang.id):
            with self.subTest(endpunkt=name):
                aufruf = getattr(self.client, methode)
                response = aufruf(url, daten, format='json') if daten else aufruf(url)
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED,
                    f'{name}: erwartet 401, bekam {response.status_code}',
                )

    def test_abgelaufene_sitzung_wirkt_sofort_auf_allen_endpunkten(self):
        self.session.gueltig_bis = timezone.now() - timedelta(minutes=1)
        self.session.save(update_fields=['gueltig_bis'])

        for name, methode, url, daten in _fuenf_endpunkte(self.vorgang.id):
            with self.subTest(endpunkt=name):
                aufruf = getattr(self.client, methode)
                response = aufruf(url, daten, format='json') if daten else aufruf(url)
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED,
                    f'{name}: erwartet 401, bekam {response.status_code}',
                )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalRateLimitTest(APITestCase):
    """Test 4: ``portal_vorgang_erstellen`` (20/Tag) zählt JE PORTAL-
    IDENTITÄT — Kontingent von A erschöpft blockiert B nicht. GET auf
    derselben View bleibt ungethrottelt."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('rate-tester')
        self.typ = _typ('rate-typ')

        self.person_a = erstelle_eigentuemer(
            nachname='RateA', email='rate-a@example.org', personennummer='P-RATE-A',
        )
        self.person_b = erstelle_eigentuemer(
            nachname='RateB', email='rate-b@example.org', personennummer='P-RATE-B',
        )
        self.weg = erstelle_objekt('RATE-A', 'WEG Rateweg 1')
        self.einheit_a = erstelle_einheit(self.weg, '0001')
        self.einheit_b = erstelle_einheit(self.weg, '0002')
        verknuepfe(self.person_a, self.einheit_a)
        verknuepfe(self.person_b, self.einheit_b)

        _, token_a = zugang_service.lade_ein(self.person_a)
        self.session_a, _, _ = zugang_service.melde_an(token_a.token)

    def _als(self, session):
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def _post(self, einheit):
        return self.client.post(VORGAENGE_URL, {
            'typ_id': str(self.typ.id), 'betreff': 'Ratelimit-Test',
            'einheit_id': str(einheit.id),
        }, format='json')

    def test_kontingent_ist_pro_identitaet_getrennt_und_get_bleibt_ungethrottelt(self):
        self._als(self.session_a)

        for i in range(20):
            response = self._post(self.einheit_a)
            self.assertEqual(
                response.status_code, status.HTTP_201_CREATED,
                f'Anlage {i + 1}/20 für A sollte noch erlaubt sein: {response.data}',
            )

        # 21. Anlage von A: Kontingent erschöpft.
        response = self._post(self.einheit_a)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # GET auf derselben View bleibt ungethrottelt, obwohl POST blockiert ist.
        response = self.client.get(VORGAENGE_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # B hat ein eigenes, noch unangetastetes Kontingent.
        _, token_b = zugang_service.lade_ein(self.person_b)
        session_b, _, _ = zugang_service.melde_an(token_b.token)
        self._als(session_b)
        response = self._post(self.einheit_b)
        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED,
            f'B darf trotz erschöpftem Kontingent von A weiter anlegen: {response.data}',
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalSchemaKeineInternenFelderTest(APITestCase):
    """Test 5: rekursiver Schema-Test — keiner der laut Spec verbotenen
    Schlüssel darf auf irgendeiner Verschachtelungstiefe der Antwort der
    fünf Endpunkte auftauchen.

    Bewusst STRENGER als die bestehenden, flachen Prüfungen in
    ``test_vorgaenge.py``/``test_konto.py`` (nur oberste Ebene, nur eine
    Teilmenge der Felder) — siehe Abnahmebericht."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('schema-tester')
        self.person = erstelle_eigentuemer(personennummer='P-SCHEMA-1', email='schema@example.org')
        self.weg = erstelle_objekt('SCHEMA-A', 'WEG Schemaweg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        self.ev = verknuepfe(self.person, self.einheit)

        self.typ = _typ('schema-typ')
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Wasserschaden', beschreibung='Details.',
            erstellt_von=self.mitarbeiter, objekt=self.weg, einheit=self.einheit,
            portal_sichtbar=True, faellig_am=date.today() + timedelta(days=3),
            mail_referenz='<ref@example.org>', telefon_rufnummer='0151 000000',
        )
        vorgang_service.weise_zu(self.vorgang, self.mitarbeiter, self.mitarbeiter)
        vorgang_service.kommentiere(self.vorgang, 'Sichtbarer Kommentar', self.mitarbeiter, intern=False)
        vorgang_service.wechsle_status(self.vorgang, 'in_bearbeitung', erstellt_von=self.mitarbeiter)

        HausgeldSollstellung.objects.create(
            objekt=self.weg, eigentumsverhaeltnis=self.ev, erstellt_von=self.mitarbeiter,
            sollstellungs_typ='hausgeld', periode=date(2026, 1, 1),
            faellig_am=date(2026, 1, 5), opos_nr='SCHEMA-0001',
            soll_betrag='300.00', ist_betrag='50.00', status_cached='teilbezahlt',
        )

        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_vorgaenge_liste_hat_keine_verbotenen_schluessel(self):
        response = self.client.get(VORGAENGE_URL)
        gefunden = _alle_schluessel(response.data) & VERBOTENE_SCHLUESSEL
        self.assertEqual(gefunden, set())

    def test_vorgang_detail_hat_keine_verbotenen_schluessel(self):
        response = self.client.get(_detail_url(self.vorgang.id))
        gefunden = _alle_schluessel(response.data) & VERBOTENE_SCHLUESSEL
        self.assertEqual(gefunden, set())

    def test_vorgang_anlage_antwort_hat_keine_verbotenen_schluessel(self):
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(self.typ.id), 'betreff': 'Neuer Vorgang',
            'einheit_id': str(self.einheit.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        gefunden = _alle_schluessel(response.data) & VERBOTENE_SCHLUESSEL
        self.assertEqual(gefunden, set())

    def test_saldo_hat_keine_verbotenen_schluessel(self):
        response = self.client.get(SALDO_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gefunden = _alle_schluessel(response.data) & VERBOTENE_SCHLUESSEL
        self.assertEqual(gefunden, set())

    def test_faelligkeiten_hat_keine_verbotenen_schluessel(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)
        gefunden = _alle_schluessel(response.data) & VERBOTENE_SCHLUESSEL
        self.assertEqual(gefunden, set())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalKiVorschlagUndInterneEreignisseTest(APITestCase):
    """Test 6: ein ECHTER interner ``VorgangEreignis`` und ein ECHTER
    ``VorgangAntwortVorschlag`` dürfen an KEINER Stelle der Antwort
    auftauchen — auch nicht als Teilstring irgendwo im JSON.

    Die bestehende Prüfung in ``test_vorgaenge.py``
    (``test_antwort_enthaelt_keinen_antwort_vorschlag``) legt dafür NIE
    einen echten ``VorgangAntwortVorschlag``-Datensatz an; sie prüft nur,
    dass der Serializer keinen Schlüssel ``antwort_vorschlag`` ausgibt — das
    wäre auch dann grün, wenn irgendwo (z.B. über ein künftiges Feld) der
    Vorschlagstext unter einem ANDEREN Namen mitliefe. Hier wird deshalb
    zusätzlich der tatsächliche Geheimtext gesucht."""

    GEHEIMER_KI_TEXT = 'GEHEIMER-KI-ENTWURF-9f3c1a'
    GEHEIMER_INTERNER_KOMMENTAR = 'GEHEIMER-INTERNER-KOMMENTAR-7b2e4d'

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('ki-tester')
        self.person = erstelle_eigentuemer(personennummer='P-KI-1', email='ki@example.org')
        self.weg = erstelle_objekt('KI-A', 'WEG KI-Weg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        verknuepfe(self.person, self.einheit)

        self.typ = _typ('ki-typ')
        self.vorgang = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Klingel defekt', erstellt_von=self.mitarbeiter,
            objekt=self.weg, einheit=self.einheit, portal_sichtbar=True,
        )
        vorgang_service.kommentiere(
            self.vorgang, self.GEHEIMER_INTERNER_KOMMENTAR, self.mitarbeiter, intern=True,
        )
        VorgangAntwortVorschlag.objects.create(
            vorgang=self.vorgang, text_ki=self.GEHEIMER_KI_TEXT, text=self.GEHEIMER_KI_TEXT,
            status='entwurf',
        )

        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_geheimtexte_erscheinen_nirgendwo_in_der_detailantwort(self):
        response = self.client.get(_detail_url(self.vorgang.id))
        rohtext = json.dumps(response.data, default=str)
        self.assertNotIn(self.GEHEIMER_KI_TEXT, rohtext)
        self.assertNotIn(self.GEHEIMER_INTERNER_KOMMENTAR, rohtext)

    def test_geheimtexte_erscheinen_nirgendwo_in_der_listenantwort(self):
        response = self.client.get(VORGAENGE_URL)
        rohtext = json.dumps(response.data, default=str)
        self.assertNotIn(self.GEHEIMER_KI_TEXT, rohtext)
        self.assertNotIn(self.GEHEIMER_INTERNER_KOMMENTAR, rohtext)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalSichtbarkeitHaertungDetailTest(APITestCase):
    """Test 7 (Ergänzung): ``portal_sichtbar=False`` ist auch über die
    Detail-Route nie erreichbar — selbst für die EIGENE Einheit."""

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('sichtbarkeit-tester')
        self.person = erstelle_eigentuemer(personennummer='P-SICHT-1', email='sicht@example.org')
        self.weg = erstelle_objekt('SICHT-A', 'WEG Sichtweg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        verknuepfe(self.person, self.einheit)

        self.typ = _typ('sicht-typ')
        self.nicht_freigegeben = vorgang_service.erstelle_vorgang(
            typ=self.typ, betreff='Interner Vermerk', erstellt_von=self.mitarbeiter,
            objekt=self.weg, einheit=self.einheit, portal_sichtbar=False,
        )

        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_nicht_freigegebener_eigener_vorgang_liefert_404_per_detail(self):
        response = self.client.get(_detail_url(self.nicht_freigegeben.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nicht_freigegebener_eigener_vorgang_fehlt_in_der_liste(self):
        response = self.client.get(VORGAENGE_URL)
        ids = {eintrag['id'] for eintrag in response.data}
        self.assertNotIn(str(self.nicht_freigegeben.id), ids)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalAnlageBodyInjectionTest(APITestCase):
    """Test 8: die Anlage darf über den Body NICHT ``portal_sichtbar``,
    ``quelle``, ``status`` oder ``erstellt_von`` überschreiben — Kontrolle
    direkt am angelegten DB-Objekt, nicht nur an der Antwort."""

    def setUp(self):
        cache.clear()
        self.person = erstelle_eigentuemer(personennummer='P-INJ-1', email='inj@example.org')
        self.fremder_mitarbeiter = _mitarbeiter('injection-fremd')
        self.weg = erstelle_objekt('INJ-A', 'WEG Injectionweg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        verknuepfe(self.person, self.einheit)

        self.typ = _typ('inj-typ')

        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_body_injection_ueberschreibt_keines_der_festen_felder(self):
        response = self.client.post(VORGAENGE_URL, {
            'typ_id': str(self.typ.id),
            'betreff': 'Body-Injection-Test',
            'einheit_id': str(self.einheit.id),
            'quelle': 'manuell',
            'status': 'erledigt',
            'portal_sichtbar': False,
            'erstellt_von': str(self.fremder_mitarbeiter.id),
            'erstellt_von_id': str(self.fremder_mitarbeiter.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        vorgang = Vorgang.objects.get(id=response.data['id'])
        self.assertEqual(vorgang.quelle, 'portal')
        self.assertEqual(vorgang.status, 'offen')
        self.assertTrue(vorgang.portal_sichtbar)
        self.assertEqual(vorgang.erstellt_von_id, vorgang_service.portal_system_user().id)
        self.assertNotEqual(vorgang.erstellt_von_id, self.fremder_mitarbeiter.id)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalFaelligkeitenPaginationTest(APITestCase):
    """Test 9: Pagination liefert bei mehr als ``page_size`` (50) offenen
    Posten korrekt ``count``/``next`` und nicht mehr als ``page_size``
    Einträge je Seite."""

    ANZAHL_POSTEN = 51

    def setUp(self):
        cache.clear()
        self.mitarbeiter = _mitarbeiter('pagination-tester')
        self.person = erstelle_eigentuemer(personennummer='P-PAGE-1', email='page@example.org')
        self.weg = erstelle_objekt('PAGE-A', 'WEG Pageweg 1')
        self.einheit = erstelle_einheit(self.weg, '0001')
        self.ev = verknuepfe(self.person, self.einheit)

        for i in range(self.ANZAHL_POSTEN):
            periode = date(2026, 1, 1) + timedelta(days=31 * i)
            HausgeldSollstellung.objects.create(
                objekt=self.weg, eigentumsverhaeltnis=self.ev, erstellt_von=self.mitarbeiter,
                sollstellungs_typ='hausgeld', periode=periode,
                faellig_am=periode + timedelta(days=4), opos_nr=f'PAGE-{i:04d}',
                soll_betrag='100.00', status_cached='offen',
            )

        _, token = zugang_service.lade_ein(self.person)
        session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {session.token}')

    def test_erste_seite_liefert_page_size_eintraege_und_count_und_next(self):
        response = self.client.get(FAELLIGKEITEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], self.ANZAHL_POSTEN)
        self.assertEqual(len(response.data['results']), 50)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])

    def test_zweite_seite_liefert_den_rest(self):
        response = self.client.get(FAELLIGKEITEN_URL, {'page': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), self.ANZAHL_POSTEN - 50)
        self.assertIsNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])
