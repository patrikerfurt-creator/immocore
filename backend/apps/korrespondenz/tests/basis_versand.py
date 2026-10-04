"""Gemeinsame Testbasis für Phase 4 (Erstellung, Versand, Druckstapel, Serienlauf).

Echte PDFs (WeasyPrint) in einem temporären ``MEDIA_ROOT``; E-Mails landen im
``locmem``-Backend der Django-Tests (``mail.outbox``).
"""
import shutil
import tempfile
from datetime import date
from itertools import count

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.korrespondenz.models import Vorlage, VorlagenVersion
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person

from . import fixtures, fixtures_brief

User = get_user_model()
_n = count(1)

KURZER_TEXT = [{'typ': 'text', 'inhalt': 'wir informieren Sie über den Stand.'}]


def neue_person(nachname='Muster', *, email='', zustimmung=False, ort='Frankfurt am Main', **felder):
    n = next(_n)
    person = Person.objects.create(
        personennummer=f'PT{n:05d}', person_typ='100', anrede='Herr', vorname='Hans',
        nachname=nachname, strasse='Testweg', hausnummer=str(n), plz='60311', ort=ort,
        emails=[{'adresse': email}] if email else [],
        zustellweg='email' if zustimmung else 'post',
        zustellweg_zustimmung_am=timezone.now() if zustimmung else None,
        **felder,
    )
    return person


def neue_einheit(objekt, nr, *, typ='Wohnung', lage=None):
    return Einheit.objects.create(
        objekt=objekt, einheit_nr=nr, flaechennummer=f'{int(nr):04d}', einheit_typ=typ,
        lage=f'Wohnung {nr}' if lage is None else lage,
    )


def neues_ev(einheit, person, beginn=date(2020, 1, 1), ende=None):
    return EigentumsVerhaeltnis.objects.create(einheit=einheit, person=person, beginn=beginn, ende=ende)


class VersandTestBasis(TestCase):
    """Szenario (WEG mit Zahlungsverkehrskonto), Standard-Briefbogen, Sachbearbeiter."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='korr_test_media_')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.s = fixtures.szenario(wechsel=False, mahnung=False, vorgang=False)
        cls.user = User.objects.create_user('sachbearbeiter', first_name='Sabine', last_name='Sachbearbeiter')
        cls.briefbogen = fixtures_brief.demme_briefbogen(cls.s.ersteller)

    # --- Hilfen ---
    def vorlage(self, code='eigentuemer_allgemein', anlass=None, *, kanal_standard='brief',
                inhalt=None, eingabefelder=None, einzeln_bearbeitbar=False, objekt=None,
                begleittext='') -> VorlagenVersion:
        vorlage = Vorlage.objects.create(
            code=code, bezeichnung=f'Vorlage {code}', anlass=anlass or code, objekt=objekt,
            kanal_standard=kanal_standard, einzeln_bearbeitbar=einzeln_bearbeitbar,
        )
        version = VorlagenVersion.objects.create(
            vorlage=vorlage, version=1, betreff='Information zum Objekt',
            inhalt=KURZER_TEXT if inhalt is None else inhalt,
            eingabefelder=eingabefelder or [], status='freigegeben',
            freigegeben_am=timezone.now(), email_begleittext=begleittext,
        )
        vorlage.aktive_version = version
        vorlage.save(update_fields=['aktive_version'])
        return version

    def mail_aktiv(self, objekt=None, aktiv=True):
        objekt = objekt or self.s.objekt
        Objekt.objects.filter(pk=objekt.pk).update(mailversand_aktiv=aktiv)

    def mail_person(self, nachname='Mailer', email='mailer@example.org'):
        return neue_person(nachname, email=email, zustimmung=True)
