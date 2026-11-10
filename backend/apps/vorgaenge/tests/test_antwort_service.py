"""Tests für ``apps.vorgaenge.services.antwort_service`` und den
``/vorgaenge/<id>/antwort/``-Endpunkt (Chat-Antworten an den Kunden).

Deckt ab:
  - gib_antwort_frei: Ereignis ``antwort_freigegeben`` (intern=False), leerer
    Text -> Fehler.
  - portal_antwort: Ereignis ``portal_antwort`` (intern=False).
  - sende_mail_antwort: Versand (locmem), Empfänger + Vorgangsnummer im Betreff,
    Ereignis ``mail_antwort_gesendet`` (intern=False); fehlende Empfänger-
    adresse und nicht konfigurierter Versand -> Fehler (ohne Ereignis/Mail).
  - API: POST /vorgaenge/<id>/antwort/ für beide Kanäle, ungültiger Kanal -> 400.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.objekte.models import Objekt
from apps.personen.models import Person
from apps.vorgaenge.models import VorgangEreignis, VorgangTyp
from apps.vorgaenge.services import antwort_service, vorgang_service

User = get_user_model()

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'
KONSOLE = 'django.core.mail.backends.console.EmailBackend'


def _objekt(nr='ANT001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Antwort', objektnummer=nr, objekt_typ='weg',
        ort='Teststadt', verwaltung_seit=date(2020, 1, 1),
    )


def _user(username='antwort-tester'):
    return User.objects.create_user(username=username, password='x')


def _typ(code='anfrage'):
    return VorgangTyp.objects.get(code=code)


def _person(email='kunde@example.org'):
    emails = [{'adresse': email}] if email else []
    return Person.objects.create(person_typ='100', nachname='Kunde', vorname='Karl', emails=emails)


def _vorgang(person=None):
    return vorgang_service.erstelle_vorgang(
        typ=_typ(), betreff='Wassereintritt am Fenster',
        beschreibung='Im Bad tritt Wasser ein.', erstellt_von=_user('ersteller'),
        objekt=_objekt(), person=person or _person(),
    )


class GibAntwortFreiTest(TestCase):
    def test_erzeugt_eigentuemer_sichtbares_ereignis(self):
        vorgang = _vorgang()
        user = _user()
        ereignis = antwort_service.gib_antwort_frei(vorgang, 'Wir kümmern uns darum.', user)
        self.assertEqual(ereignis.typ, 'antwort_freigegeben')
        self.assertFalse(ereignis.intern)
        self.assertEqual(ereignis.text, 'Wir kümmern uns darum.')

    def test_leerer_text_wirft_fehler(self):
        vorgang = _vorgang()
        with self.assertRaises(ValidationError):
            antwort_service.gib_antwort_frei(vorgang, '   ', _user())


class PortalAntwortTest(TestCase):
    def test_erzeugt_portal_antwort_ereignis(self):
        vorgang = _vorgang()
        ereignis = antwort_service.portal_antwort(vorgang, 'Danke für die Rückmeldung.', _user('portal-sys'))
        self.assertEqual(ereignis.typ, 'portal_antwort')
        self.assertFalse(ereignis.intern)


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL='info@demme-immobilien.de')
class SendeMailAntwortTest(TestCase):
    def test_versendet_und_vermerkt(self):
        vorgang = _vorgang(person=_person('eigentuemer@example.org'))
        ereignis = antwort_service.sende_mail_antwort(vorgang, 'Ihre Mail-Antwort.', _user())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['eigentuemer@example.org'])
        # Vorgangsnummer im Betreff -> Kundenantwort matcht automatisch zurück.
        self.assertIn(vorgang.nummer, mail.outbox[0].subject)
        self.assertEqual(ereignis.typ, 'mail_antwort_gesendet')
        self.assertFalse(ereignis.intern)

    def test_ohne_empfaengeradresse_kein_versand(self):
        vorgang = _vorgang(person=_person(email=''))
        with self.assertRaises(ValidationError):
            antwort_service.sende_mail_antwort(vorgang, 'Text', _user())
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(VorgangEreignis.objects.filter(
            vorgang=vorgang, typ='mail_antwort_gesendet').exists())


@override_settings(EMAIL_BACKEND=KONSOLE)
class SendeMailNichtKonfiguriertTest(TestCase):
    def test_konsolen_backend_gilt_als_nicht_versandfaehig(self):
        vorgang = _vorgang(person=_person('x@example.org'))
        with self.assertRaises(ValidationError):
            antwort_service.sende_mail_antwort(vorgang, 'Text', _user())
        self.assertFalse(VorgangEreignis.objects.filter(
            vorgang=vorgang, typ='mail_antwort_gesendet').exists())


@override_settings(EMAIL_BACKEND=LOCMEM, DEFAULT_FROM_EMAIL='info@demme-immobilien.de')
class AntwortApiTest(APITestCase):
    def setUp(self):
        self.user = _user('api-tester')
        self.client.force_authenticate(self.user)
        self.vorgang = _vorgang(person=_person('api@example.org'))

    def _url(self):
        return f'/api/v1/vorgaenge/{self.vorgang.id}/antwort/'

    def test_portal_kanal_gibt_frei(self):
        resp = self.client.post(self._url(), {'text': 'Portal-Antwort', 'kanal': 'portal'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(VorgangEreignis.objects.filter(
            vorgang=self.vorgang, typ='antwort_freigegeben', intern=False).exists())

    def test_mail_kanal_versendet(self):
        resp = self.client.post(self._url(), {'text': 'Mail-Antwort', 'kanal': 'mail'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(VorgangEreignis.objects.filter(
            vorgang=self.vorgang, typ='mail_antwort_gesendet', intern=False).exists())

    def test_ungueltiger_kanal_400(self):
        resp = self.client.post(self._url(), {'text': 'x', 'kanal': 'fax'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
