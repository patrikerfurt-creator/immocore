"""
Tests für das SEPA-Lastschriftmandat im Portal (Architektur-Entscheid
``docs/ARCHITEKTUR_ENTSCHEID_PORTAL_SEPA_MANDAT.md``, Abschnitte b, c, e, f).

Kernregeln, die hier abgesichert werden:
  - R3: Anfordern schreibt KEIN Mandat, erst der bestätigende POST
  - R4: Aktion (erteilen/ändern) liefert der Server je Geltungsbereich
  - R5: ungültige IBAN → keine Mail, kein Antrag
  - R6/R7: Audit mit Quelle 'Portal-Magic-Link', Person.ibans gepflegt
  - R8: ``schluessel`` wird nur gegen die EIGENE Liste aufgelöst
  - Bestätigung wirkt nie beim Öffnen des Links, nie ohne Kontoinhaber-Erklärung
"""
import hashlib
from datetime import date, timedelta
from unittest import mock as umock
from uuid import uuid4

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.personen.models import EigentumsVerhaeltnis, Person, SEPAMandat
from apps.personen.services.sepa_mandat import mandat_fuer_ev, sammelmandat_fuer_person
from apps.portal.models import (
    PersonStammdatenAenderung,
    PortalSepaMandatAenderung as Antrag,
    PortalToken,
)
from apps.portal.services import mail_service, sepa_mandat_service, zugang_service
from apps.portal.services.iban_service import normalisiere_iban, pruefe_iban
from apps.portal.services.request_info import client_ip
from apps.portal.services.sepa_mandat_text import maskiere_iban
from .basis import (
    erstelle_eigentuemer,
    erstelle_einheit,
    erstelle_mandat,
    erstelle_objekt,
    verknuepfe,
)

STATUS_URL = '/api/v1/portal/sepa-mandat/'
ANFORDERN_URL = '/api/v1/portal/sepa-mandat/anfordern/'
BESTAETIGEN_URL = '/api/v1/portal/sepa-mandat/bestaetigen/'
BANK_URL = '/api/v1/portal/meine-daten/bankverbindung/'

IBAN_A = 'DE89370400440532013000'
IBAN_B = 'DE02120300000000202051'
GLAEUBIGER_ID = 'DE98ZZZ09999999999'


def vorschau_url(token: str) -> str:
    return f'/api/v1/portal/sepa-mandat/bestaetigen/{token}/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SepaTestBasis(APITestCase):
    """Eine Person mit einer Einheit in einem WEG mit Gläubiger-ID."""

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.person = erstelle_eigentuemer(email='eig@example.org')
        self.objekt = erstelle_objekt()
        self.objekt.glaeubiger_id = GLAEUBIGER_ID
        self.objekt.save(update_fields=['glaeubiger_id'])
        self.einheit = erstelle_einheit(self.objekt, '0001', 'EG links')
        self.ev = verknuepfe(self.person, self.einheit)

        self.zugang, token = zugang_service.lade_ein(self.person)
        self.session, _, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session.token}')
        # Die Bestätigung kommt aus dem Mail-Postfach, ohne Portal-Sitzung.
        self.anonym = APIClient()

    # -- Testdaten -----------------------------------------------------------

    def zweite_einheit(self, nr='0002', objekt=None, glaeubiger=True):
        if objekt is None:
            objekt = erstelle_objekt(nr='PORTAL002', bezeichnung='WEG Zweitweg 2')
            if glaeubiger:
                objekt.glaeubiger_id = 'DE11ZZZ00000000001'
                objekt.save(update_fields=['glaeubiger_id'])
        einheit = erstelle_einheit(objekt, nr, 'OG rechts')
        return verknuepfe(self.person, einheit)

    def sammelmandat(self, referenz='M2024-090', iban=IBAN_B, bic='BYLADEM1001'):
        return SEPAMandat.objects.create(
            mandatsreferenz=referenz, iban=iban, bic=bic,
            unterzeichnet_am=date(2022, 3, 1), person=self.person,
            sequence_type='RCUR',
        )

    # -- Aufrufe -------------------------------------------------------------

    def anfordern(self, schluessel='alle', iban=IBAN_A, bic='COBADEFFXXX', **extra):
        return self.client.post(
            ANFORDERN_URL, {'schluessel': schluessel, 'iban': iban, 'bic': bic},
            format='json', **extra,
        )

    def letzter_token(self) -> str:
        return PortalToken.objects.filter(
            typ=PortalToken.TYP_SEPA_MANDAT,
        ).order_by('-erstellt_am').first().token

    def bestaetigen(self, token, erklaerung=True, **extra):
        # on_commit-Callbacks (Bestätigungsmail) laufen im TestCase nicht von allein.
        with self.captureOnCommitCallbacks(execute=True):
            return self.anonym.post(
                BESTAETIGEN_URL,
                {'token': token, 'kontoinhaber_erklaerung': erklaerung},
                format='json', **extra,
            )

    def anfordern_und_bestaetigen(self, schluessel='alle', iban=IBAN_A, bic='COBADEFFXXX'):
        antwort = self.anfordern(schluessel, iban, bic)
        self.assertEqual(antwort.status_code, status.HTTP_200_OK, antwort.data)
        return self.bestaetigen(self.letzter_token())

    def alle_eintraege(self, feld):
        return PersonStammdatenAenderung.objects.filter(person=self.person, feld=feld)

    def assertKeinPortalMandat(self):
        self.assertFalse(SEPAMandat.objects.filter(quelle=SEPAMandat.QUELLE_PORTAL).exists())


# ---------------------------------------------------------------------------
# Status (GET /portal/sepa-mandat/)
# ---------------------------------------------------------------------------

class SepaStatusTest(SepaTestBasis):
    def test_eine_einheit_ohne_mandat(self):
        antwort = self.client.get(STATUS_URL)

        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        d = antwort.data
        self.assertTrue(d['kann_erteilen'])
        self.assertIsNone(d['hinderungsgrund'])
        self.assertFalse(d['auswahl_noetig'])
        self.assertEqual(d['kopfzeile_aktion'], 'erteilen')
        self.assertEqual(d['empfaenger_email_maskiert'], 'e***@example.org')
        self.assertIsNone(d['offene_anfrage'])
        self.assertEqual(len(d['geltungsbereiche']), 1)
        eintrag = d['geltungsbereiche'][0]
        self.assertEqual(eintrag['schluessel'], 'alle')
        self.assertEqual(eintrag['aktion'], 'erteilen')
        self.assertIsNone(eintrag['mandat'])
        self.assertIsNone(eintrag['ev_id'])

    def test_zwei_einheiten_mit_sammelmandat(self):
        ev2 = self.zweite_einheit()
        self.sammelmandat()

        d = self.client.get(STATUS_URL).data

        self.assertTrue(d['auswahl_noetig'])
        self.assertEqual(d['kopfzeile_aktion'], 'aendern')
        eintraege = {e['schluessel']: e for e in d['geltungsbereiche']}
        self.assertEqual(set(eintraege), {'alle', f'ev:{self.ev.id}', f'ev:{ev2.id}'})

        alle = eintraege['alle']
        self.assertEqual(alle['aktion'], 'aendern')
        self.assertEqual(alle['mandat']['mandatsreferenz'], 'M2024-090')
        self.assertEqual(alle['mandat']['iban_maskiert'], 'DE02 **** **** **** **20 51')
        self.assertEqual(alle['mandat']['quelle'], 'verwaltung')

        for ev in (self.ev, ev2):
            e = eintraege[f'ev:{ev.id}']
            self.assertEqual(e['aktion'], 'erteilen')
            self.assertEqual(e['wirksam_ueber'], 'alle')
            self.assertIsNone(e['mandat'])
            self.assertEqual(e['ev_id'], str(ev.id))
        self.assertEqual(eintraege[f'ev:{ev2.id}']['einheit_nr'], '0002')
        self.assertEqual(eintraege[f'ev:{ev2.id}']['objekt_bezeichnung'], 'WEG Zweitweg 2')
        self.assertEqual(eintraege[f'ev:{ev2.id}']['lage'], 'OG rechts')

    def test_zwei_einheiten_ohne_mandat_wirksam_ueber_keins(self):
        self.zweite_einheit()
        d = self.client.get(STATUS_URL).data
        self.assertEqual(d['kopfzeile_aktion'], 'erteilen')
        ev_eintraege = [e for e in d['geltungsbereiche'] if e['schluessel'] != 'alle']
        self.assertTrue(all(e['wirksam_ueber'] == 'keins' for e in ev_eintraege))

    def test_legacy_mandat_wird_als_sammelmandat_erkannt(self):
        erstelle_mandat(self.person, referenz='LEGACY-1')  # nur Person.sepa_mandat

        d = self.client.get(STATUS_URL).data

        self.assertTrue(d['kann_erteilen'])
        eintrag = d['geltungsbereiche'][0]
        self.assertEqual(eintrag['schluessel'], 'alle')
        self.assertEqual(eintrag['aktion'], 'aendern')
        self.assertEqual(eintrag['mandat']['mandatsreferenz'], 'LEGACY-1')
        self.assertEqual(d['kopfzeile_aktion'], 'aendern')

    def test_einheitenmandat_bei_einer_einheit_zeigt_ev_eintrag(self):
        SEPAMandat.objects.create(
            mandatsreferenz='EV-1', iban=IBAN_B, unterzeichnet_am=date(2022, 1, 1),
            person=self.person, eigentumsverhaeltnis=self.ev,
        )
        d = self.client.get(STATUS_URL).data
        self.assertEqual(len(d['geltungsbereiche']), 1)
        eintrag = d['geltungsbereiche'][0]
        self.assertEqual(eintrag['schluessel'], f'ev:{self.ev.id}')
        self.assertEqual(eintrag['aktion'], 'aendern')
        self.assertEqual(eintrag['wirksam_ueber'], 'einheit')
        self.assertEqual(eintrag['mandat']['mandatsreferenz'], 'EV-1')

    def test_objekt_ohne_glaeubiger_id_blockiert(self):
        self.objekt.glaeubiger_id = ''
        self.objekt.save(update_fields=['glaeubiger_id'])

        d = self.client.get(STATUS_URL).data

        self.assertFalse(d['kann_erteilen'])
        self.assertIn('Gläubiger-ID', d['hinderungsgrund'])

    def test_ohne_eigene_email_blockiert(self):
        self.person.email = ''
        self.person.emails = []
        self.person.save(update_fields=['email', 'emails'])

        d = self.client.get(STATUS_URL).data

        self.assertFalse(d['kann_erteilen'])
        self.assertIn('E-Mail', d['hinderungsgrund'])
        self.assertIsNone(d['empfaenger_email_maskiert'])

    def test_ohne_aktives_ev_blockiert(self):
        self.ev.ende = date(2022, 12, 31)
        self.ev.save(update_fields=['ende'])

        d = self.client.get(STATUS_URL).data

        self.assertFalse(d['kann_erteilen'])
        self.assertEqual(d['geltungsbereiche'], [])

    def test_geteiltes_mandat_blockiert(self):
        mandat = erstelle_mandat(self.person, referenz='GETEILT-1')
        partner = erstelle_eigentuemer(
            nachname='Partner', email='partner@example.org', personennummer='P-PORTAL-9',
        )
        partner.sepa_mandat = mandat
        partner.save(update_fields=['sepa_mandat'])

        d = self.client.get(STATUS_URL).data

        self.assertFalse(d['kann_erteilen'])
        self.assertIn('Verwaltung', d['hinderungsgrund'])
        self.assertEqual(self.anfordern().status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_verweis_auf_mandat_einer_anderen_person_gilt_nicht(self):
        """Der Resolver ignoriert fremde Mandate; das Portal behandelt die
        Person als ohne Mandat und fasst das fremde Mandat nie an."""
        andere = erstelle_eigentuemer(
            nachname='Andere', email='andere@example.org', personennummer='P-PORTAL-8',
        )
        mandat = SEPAMandat.objects.create(
            mandatsreferenz='FREMD-1', iban=IBAN_B, unterzeichnet_am=date(2022, 1, 1),
            person=andere,
        )
        self.person.sepa_mandat = mandat
        self.person.save(update_fields=['sepa_mandat'])

        d = self.client.get(STATUS_URL).data

        self.assertTrue(d['kann_erteilen'])
        self.assertEqual(d['geltungsbereiche'][0]['aktion'], 'erteilen')
        self.assertIsNone(d['geltungsbereiche'][0]['mandat'])

    def test_beendetes_ev_wird_nicht_angeboten(self):
        alt = self.zweite_einheit()
        alt.ende = date(2023, 1, 1)
        alt.save(update_fields=['ende'])
        d = self.client.get(STATUS_URL).data
        self.assertFalse(d['auswahl_noetig'])
        self.assertEqual([e['schluessel'] for e in d['geltungsbereiche']], ['alle'])

    def test_ev_mit_kuenftigem_ende_zaehlt_noch(self):
        self.ev.ende = timezone.localdate() + timedelta(days=30)
        self.ev.save(update_fields=['ende'])
        self.assertTrue(self.client.get(STATUS_URL).data['kann_erteilen'])

    def test_fremde_einheiten_tauchen_nicht_auf(self):
        fremder = erstelle_eigentuemer(
            nachname='Fremd', email='fremd@example.org', personennummer='P-PORTAL-7',
        )
        fremde_ev = verknuepfe(fremder, erstelle_einheit(self.objekt, '0099', 'DG'))
        d = self.client.get(STATUS_URL).data
        self.assertNotIn(f'ev:{fremde_ev.id}', [e['schluessel'] for e in d['geltungsbereiche']])

    def test_offene_anfrage_wird_angezeigt(self):
        self.anfordern()
        d = self.client.get(STATUS_URL).data
        self.assertEqual(d['offene_anfrage']['schluessel'], 'alle')
        self.assertEqual(d['offene_anfrage']['aktion'], 'erteilen')
        self.assertIsNotNone(d['offene_anfrage']['gueltig_bis'])

    def test_abgelaufene_anfrage_wird_lazy_auf_verfallen_gesetzt(self):
        self.anfordern()
        PortalToken.objects.filter(typ=PortalToken.TYP_SEPA_MANDAT).update(
            gueltig_bis=timezone.now() - timedelta(minutes=1),
        )

        d = self.client.get(STATUS_URL).data

        self.assertIsNone(d['offene_anfrage'])
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_VERFALLEN)

    def test_ohne_sitzung_401(self):
        self.client.credentials()
        self.assertEqual(self.client.get(STATUS_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.anfordern().status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Anfordern
# ---------------------------------------------------------------------------

class SepaAnfordernTest(SepaTestBasis):
    def test_anlage_sammelmandat_versendet_mail_und_legt_nur_einen_antrag_an(self):
        antwort = self.anfordern(
            HTTP_USER_AGENT='TestBrowser/1.0', HTTP_X_REAL_IP='203.0.113.7',
        )

        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        self.assertEqual(antwort.data['empfaenger_email_maskiert'], 'e***@example.org')
        self.assertIn('e***@example.org', antwort.data['detail'])
        self.assertIn('gueltig_bis', antwort.data)

        # genau eine Mail, an die EIGENE Adresse, mit Link auf die Bestätigungsseite
        self.assertEqual(len(mail.outbox), 1)
        nachricht = mail.outbox[0]
        self.assertEqual(nachricht.to, ['eig@example.org'])
        self.assertEqual(nachricht.subject, 'Bitte bestätigen Sie Ihr SEPA-Lastschriftmandat')
        token = self.letzter_token()
        url = f'/portal/sepa-mandat/bestaetigen/{token}'
        self.assertIn(url, nachricht.body)
        self.assertIn(url, nachricht.alternatives[0][0])
        self.assertIn(GLAEUBIGER_ID, nachricht.body)

        # R3: KEIN Mandat
        self.assertEqual(SEPAMandat.objects.count(), 0)

        antrag = Antrag.objects.get()
        self.assertEqual(antrag.status, Antrag.STATUS_OFFEN)
        self.assertEqual(antrag.aktion, Antrag.AKTION_ANLAGE)
        self.assertEqual(antrag.geltungsbereich, Antrag.GELTUNG_ALLE)
        self.assertIsNone(antrag.eigentumsverhaeltnis)
        self.assertTrue(antrag.mandatsreferenz.startswith('PORTAL-'))
        self.assertTrue(antrag.mandatsreferenz.endswith('-001'))
        self.assertLessEqual(len(antrag.mandatsreferenz), 31)
        self.assertEqual(antrag.iban, IBAN_A)
        self.assertEqual(antrag.bic, 'COBADEFFXXX')
        self.assertEqual(antrag.kontoinhaber_name, self.person.name)
        self.assertEqual(antrag.empfaenger_email, 'eig@example.org')
        self.assertIsNotNone(antrag.mail_versendet_am)
        self.assertEqual(antrag.anforderung_ip, '203.0.113.7')
        self.assertEqual(antrag.anforderung_user_agent, 'TestBrowser/1.0')
        self.assertEqual(antrag.portal_session_id, self.session.id)
        self.assertEqual(antrag.token.token, token)
        self.assertEqual(antrag.mandatstext_version, 'SEPA-CORE-PORTAL-1')
        self.assertEqual(
            antrag.mandatstext_sha256,
            hashlib.sha256(antrag.mandatstext.encode('utf-8')).hexdigest(),
        )
        self.assertEqual(antrag.abgedeckte_glaeubiger, [{
            'objekt_id': str(self.objekt.id), 'bezeichnung': 'WEG Portalweg 1',
            'glaeubiger_id': GLAEUBIGER_ID, 'ev_ids': [str(self.ev.id)],
        }])

    def test_mandatstext_enthaelt_die_pflichtangaben(self):
        self.anfordern()
        antrag = Antrag.objects.get()
        text = antrag.mandatstext
        for erwartet in (
            'WEG Portalweg 1', GLAEUBIGER_ID, 'Demme Immobilien Verwaltung GmbH',
            antrag.mandatsreferenz, self.person.name,
            'DE89 3704 0044 0532 0130 00', 'COBADEFFXXX',
            'wiederkehrende Zahlungen', 'acht Wochen', 'Vorabankündigung',
        ):
            self.assertIn(erwartet, text)
        # identisch in der Mail
        self.assertIn(text.splitlines()[0], mail.outbox[0].body)
        self.assertIn('acht Wochen', mail.outbox[0].body)

    def test_token_ist_24_stunden_gueltig(self):
        self.anfordern()
        token = PortalToken.objects.get(typ=PortalToken.TYP_SEPA_MANDAT)
        rest = token.gueltig_bis - timezone.now()
        self.assertGreater(rest, timedelta(hours=23, minutes=55))
        self.assertLessEqual(rest, timedelta(hours=24))

    def test_ungueltige_iban_wird_abgelehnt_ohne_mail(self):
        antwort = self.anfordern(iban='DE89370400440532013001')

        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(antwort.data['detail'], 'Diese IBAN ist ungültig.')
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Antrag.objects.count(), 0)
        self.assertEqual(PortalToken.objects.filter(typ=PortalToken.TYP_SEPA_MANDAT).count(), 0)

    def test_ungueltige_bic_wird_abgelehnt(self):
        self.assertEqual(self.anfordern(bic='123').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_bic_ist_optional(self):
        antwort = self.client.post(
            ANFORDERN_URL, {'schluessel': 'alle', 'iban': IBAN_A}, format='json',
        )
        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        self.assertEqual(Antrag.objects.get().bic, '')

    def test_fremder_schluessel_wird_abgelehnt(self):
        fremder = erstelle_eigentuemer(
            nachname='Fremd', email='fremd@example.org', personennummer='P-PORTAL-7',
        )
        fremde_ev = verknuepfe(fremder, erstelle_einheit(self.objekt, '0099', 'DG'))
        self.zweite_einheit()  # auch mit Auswahl: fremde EV bleibt unbekannt

        for schluessel in (f'ev:{fremde_ev.id}', f'ev:{uuid4()}', 'ev:keine-uuid', '', 'alle2'):
            antwort = self.anfordern(schluessel=schluessel)
            self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST, schluessel)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Antrag.objects.count(), 0)

    def test_beendetes_ev_als_schluessel_wird_abgelehnt(self):
        alt = self.zweite_einheit()
        alt.ende = date(2023, 1, 1)
        alt.save(update_fields=['ende'])
        self.assertEqual(
            self.anfordern(schluessel=f'ev:{alt.id}').status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_zweites_anfordern_verwirft_das_erste_und_entwertet_den_token(self):
        self.anfordern()
        erster_token = self.letzter_token()
        erster = Antrag.objects.get()

        self.assertEqual(self.anfordern(iban=IBAN_B).status_code, status.HTTP_200_OK)

        erster.refresh_from_db()
        self.assertEqual(erster.status, Antrag.STATUS_VERWORFEN)
        self.assertEqual(erster.verworfen_grund, 'Neue Anfrage')
        self.assertIsNotNone(PortalToken.objects.get(token=erster_token).verbraucht_am)
        self.assertEqual(Antrag.objects.filter(status=Antrag.STATUS_OFFEN).count(), 1)

        # der erste Link ist tot, der zweite lebt
        self.assertEqual(
            self.bestaetigen(erster_token).status_code, status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(SEPAMandat.objects.count(), 0)
        self.assertEqual(
            self.bestaetigen(self.letzter_token()).status_code, status.HTTP_200_OK,
        )
        self.assertEqual(SEPAMandat.objects.get().iban, IBAN_B)

    def test_mailfehler_rollt_antrag_und_token_zurueck(self):
        with umock.patch.object(mail_service, '_sende', side_effect=RuntimeError('SMTP weg')):
            antwort = self.anfordern()

        self.assertEqual(antwort.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(Antrag.objects.count(), 0)
        self.assertEqual(PortalToken.objects.filter(typ=PortalToken.TYP_SEPA_MANDAT).count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_mailfehler_beim_zweiten_anfordern_laesst_die_erste_anfrage_bestehen(self):
        self.anfordern()
        erster_token = self.letzter_token()
        with umock.patch.object(mail_service, '_sende', side_effect=RuntimeError('SMTP weg')):
            self.anfordern()

        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_OFFEN)
        self.assertIsNone(PortalToken.objects.get(token=erster_token).verbraucht_am)

    def test_versand_nicht_konfiguriert_ist_503(self):
        with umock.patch.object(
            mail_service, '_sende', side_effect=mail_service.VersandNichtKonfiguriert('kein SMTP'),
        ):
            antwort = self.anfordern()
        self.assertEqual(antwort.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(Antrag.objects.count(), 0)

    def test_throttle_sechste_anfrage_pro_stunde_ist_429(self):
        for _ in range(5):
            self.assertEqual(self.anfordern().status_code, status.HTTP_200_OK)
        self.assertEqual(self.anfordern().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_einheitenmandat_anfordern(self):
        ev2 = self.zweite_einheit()
        antwort = self.anfordern(schluessel=f'ev:{ev2.id}')

        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        antrag = Antrag.objects.get()
        self.assertEqual(antrag.geltungsbereich, Antrag.GELTUNG_EINHEIT)
        self.assertEqual(antrag.eigentumsverhaeltnis, ev2)
        self.assertEqual([g['glaeubiger_id'] for g in antrag.abgedeckte_glaeubiger], ['DE11ZZZ00000000001'])
        self.assertIn('Einheit 0002', antrag.mandatstext)
        self.assertNotIn(GLAEUBIGER_ID, antrag.mandatstext)

    def test_sammelmandat_deckt_alle_aktiven_weg_ab(self):
        self.zweite_einheit()
        self.anfordern()
        antrag = Antrag.objects.get()
        self.assertEqual(
            sorted(g['glaeubiger_id'] for g in antrag.abgedeckte_glaeubiger),
            sorted([GLAEUBIGER_ID, 'DE11ZZZ00000000001']),
        )

    def test_aenderung_nutzt_die_referenz_des_bestehenden_mandats(self):
        mandat = self.sammelmandat()
        antwort = self.anfordern()

        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        antrag = Antrag.objects.get()
        self.assertEqual(antrag.aktion, Antrag.AKTION_AENDERUNG)
        self.assertEqual(antrag.ziel_mandat, mandat)
        self.assertEqual(antrag.mandatsreferenz, 'M2024-090')
        self.assertIn('Änderung der Kontoverbindung', antrag.mandatstext)
        self.assertEqual(mail.outbox[0].to, ['eig@example.org'])

    def test_laufende_nummer_der_referenz_zaehlt_hoch(self):
        self.anfordern_und_bestaetigen()
        erste = SEPAMandat.objects.get().mandatsreferenz
        self.assertTrue(erste.endswith('-001'))

        ev2 = self.zweite_einheit()
        self.anfordern(schluessel=f'ev:{ev2.id}', iban=IBAN_B)
        zweite = Antrag.objects.filter(status=Antrag.STATUS_OFFEN).get().mandatsreferenz
        self.assertEqual(zweite, erste[:-3] + '002')

    def test_ohne_personennummer_format_wird_hexkennung_verwendet(self):
        referenz = sepa_mandat_service.erzeuge_mandatsreferenz(self.person)
        # 'P-PORTAL-1' enthält Zeichen außerhalb A-Z0-9 → 'P' + 10 Hex der UUID
        self.assertRegex(referenz, r'^PORTAL-P[0-9A-F]{10}-001$')
        self.assertLessEqual(len(referenz), 31)

    def test_referenz_mit_gueltiger_personennummer(self):
        p = Person.objects.create(
            personennummer='100234', person_typ='100', vorname='A', nachname='B',
        )
        self.assertEqual(sepa_mandat_service.erzeuge_mandatsreferenz(p), 'PORTAL-100234-001')

    def test_leerer_schluessel_oder_iban_ist_400(self):
        antwort = self.client.post(ANFORDERN_URL, {'schluessel': 'alle'}, format='json')
        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Vorschau
# ---------------------------------------------------------------------------

class SepaVorschauTest(SepaTestBasis):
    def test_vorschau_liefert_text_und_verbraucht_den_token_nicht(self):
        self.anfordern()
        token = self.letzter_token()

        for _ in range(2):
            antwort = self.anonym.get(vorschau_url(token))
            self.assertEqual(antwort.status_code, status.HTTP_200_OK)

        d = antwort.data
        antrag = Antrag.objects.get()
        self.assertEqual(d['mandatstext'], antrag.mandatstext)
        self.assertEqual(d['mandatsreferenz'], antrag.mandatsreferenz)
        self.assertEqual(d['iban_maskiert'], 'DE89 **** **** **** **30 00')
        self.assertEqual(d['bic'], 'COBADEFFXXX')
        self.assertEqual(d['geltungsbereich'], 'alle')
        self.assertEqual(d['geltungsbereich_text'], 'Alle Ihre Einheiten (Sammelmandat)')
        self.assertEqual(d['aktion'], 'erteilen')
        self.assertEqual(d['kontoinhaber_name'], self.person.name)
        self.assertIsNotNone(d['gueltig_bis'])
        self.assertIsNone(PortalToken.objects.get(token=token).verbraucht_am)
        self.assertEqual(SEPAMandat.objects.count(), 0)

        # danach funktioniert die Bestätigung
        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_200_OK)

    def test_vorschau_unbekannter_token(self):
        antwort = self.anonym.get(vorschau_url('gibt-es-nicht'))
        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(antwort.data['detail'], 'Dieser Link ist ungültig oder abgelaufen.')

    def test_vorschau_falscher_token_typ(self):
        self.client.post('/api/v1/portal/meine-daten/email/', {'email': 'neu@example.org'})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EMAIL_BESTAETIGUNG)
        self.assertEqual(
            self.anonym.get(vorschau_url(token.token)).status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_vorschau_nach_verwerfen_ungueltig(self):
        self.anfordern()
        erster = self.letzter_token()
        self.anfordern()
        self.assertEqual(
            self.anonym.get(vorschau_url(erster)).status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_vorschau_abgelaufen(self):
        self.anfordern()
        token = self.letzter_token()
        PortalToken.objects.filter(token=token).update(gueltig_bis=timezone.now() - timedelta(minutes=1))
        self.assertEqual(
            self.anonym.get(vorschau_url(token)).status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_vorschau_gesperrter_zugang(self):
        self.anfordern()
        token = self.letzter_token()
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])
        self.assertEqual(
            self.anonym.get(vorschau_url(token)).status_code, status.HTTP_400_BAD_REQUEST,
        )


# ---------------------------------------------------------------------------
# Bestätigen: Wirkung
# ---------------------------------------------------------------------------

class SepaBestaetigenTest(SepaTestBasis):
    def test_anlage_sammelmandat(self):
        self.anfordern(HTTP_USER_AGENT='MailBrowser/2')
        antrag_vorher = Antrag.objects.get()

        antwort = self.bestaetigen(
            self.letzter_token(),
            HTTP_USER_AGENT='Bestaetiger/3',
            HTTP_X_REAL_IP='198.51.100.4',
            HTTP_X_FORWARDED_FOR='198.51.100.4, 10.0.0.1',
        )

        self.assertEqual(antwort.status_code, status.HTTP_200_OK, antwort.data)
        self.assertEqual(antwort.data['mandatsreferenz'], antrag_vorher.mandatsreferenz)
        self.assertEqual(antwort.data['aktion'], 'erteilen')
        self.assertEqual(antwort.data['geltungsbereich_text'], 'Alle Ihre Einheiten (Sammelmandat)')

        mandat = SEPAMandat.objects.get()
        self.assertEqual(mandat.mandatsreferenz, antrag_vorher.mandatsreferenz)
        self.assertEqual(mandat.person, self.person)
        self.assertIsNone(mandat.eigentumsverhaeltnis)
        self.assertTrue(mandat.ist_sammelmandat)
        self.assertEqual(mandat.sequence_type, 'RCUR')
        self.assertEqual(mandat.quelle, SEPAMandat.QUELLE_PORTAL)
        self.assertEqual(mandat.unterzeichnet_am, timezone.localdate())
        self.assertEqual(mandat.iban, IBAN_A)
        self.assertEqual(mandat.bic, 'COBADEFFXXX')
        self.assertTrue(mandat.aktiv)

        self.person.refresh_from_db()
        self.assertEqual(self.person.sepa_mandat, mandat)
        self.assertEqual(self.person.ibans[0], IBAN_A)  # R7
        self.assertEqual(sammelmandat_fuer_person(self.person), mandat)
        self.assertEqual(mandat_fuer_ev(self.ev), mandat)

        # R6
        eintrag = self.alle_eintraege('sepa_mandat').get()
        self.assertEqual(eintrag.quelle, 'Portal-Magic-Link')
        self.assertEqual(eintrag.alter_wert, '')
        antrag = Antrag.objects.get()
        self.assertIn(f'Nachweis {antrag.id}', eintrag.neuer_wert)
        self.assertIn(mandat.mandatsreferenz, eintrag.neuer_wert)
        self.assertIn('DE89 **** **** **** **30 00', eintrag.neuer_wert)
        self.assertNotIn(IBAN_A, eintrag.neuer_wert)
        self.assertEqual(self.alle_eintraege('iban').get().quelle, 'Portal-Magic-Link')

        # Nachweis
        self.assertEqual(antrag.status, Antrag.STATUS_BESTAETIGT)
        self.assertEqual(antrag.mandat, mandat)
        self.assertIsNotNone(antrag.bestaetigt_am)
        self.assertEqual(antrag.bestaetigung_ip, '198.51.100.4')
        self.assertEqual(antrag.bestaetigung_user_agent, 'Bestaetiger/3')
        self.assertEqual(antrag.forwarded_for_roh, '198.51.100.4, 10.0.0.1')
        self.assertTrue(antrag.kontoinhaber_erklaerung)
        self.assertEqual(antrag.anforderung_user_agent, 'MailBrowser/2')
        self.assertEqual(antrag.mandatstext, antrag_vorher.mandatstext)
        self.assertIsNotNone(PortalToken.objects.get(typ=PortalToken.TYP_SEPA_MANDAT).verbraucht_am)

        # Bestätigungsmail
        self.assertEqual(len(mail.outbox), 2)
        bestaetigung = mail.outbox[1]
        self.assertEqual(bestaetigung.to, ['eig@example.org'])
        self.assertEqual(bestaetigung.subject, 'Ihr SEPA-Lastschriftmandat wurde erteilt')
        self.assertIn(mandat.mandatsreferenz, bestaetigung.body)
        self.assertIn(GLAEUBIGER_ID, bestaetigung.body)
        self.assertIn('acht Wochen', bestaetigung.body)

    def test_anlage_einheitenmandat(self):
        ev2 = self.zweite_einheit()
        antwort = self.anfordern_und_bestaetigen(schluessel=f'ev:{ev2.id}')

        self.assertEqual(antwort.status_code, status.HTTP_200_OK, antwort.data)
        self.assertIn('Einheit 0002', antwort.data['geltungsbereich_text'])
        mandat = SEPAMandat.objects.get()
        self.assertEqual(mandat.eigentumsverhaeltnis, ev2)
        self.assertEqual(mandat.person, self.person)
        self.assertFalse(mandat.ist_sammelmandat)
        self.assertEqual(mandat.sequence_type, 'RCUR')
        self.assertEqual(mandat.quelle, SEPAMandat.QUELLE_PORTAL)

        self.person.refresh_from_db()
        self.assertIsNone(self.person.sepa_mandat_id)  # Einheitenmandate fassen den Legacy-FK nie an
        self.assertEqual(mandat_fuer_ev(ev2), mandat)
        self.assertIsNone(mandat_fuer_ev(self.ev))
        self.assertIsNone(sammelmandat_fuer_person(self.person))

    def test_einheitenmandat_laesst_bestehendes_sammelmandat_und_legacy_fk_unberuehrt(self):
        sammel = self.sammelmandat()
        self.person.sepa_mandat = sammel
        self.person.save(update_fields=['sepa_mandat'])
        ev2 = self.zweite_einheit()

        self.anfordern_und_bestaetigen(schluessel=f'ev:{ev2.id}')

        self.person.refresh_from_db()
        self.assertEqual(self.person.sepa_mandat, sammel)
        einheitenmandat = SEPAMandat.objects.get(eigentumsverhaeltnis=ev2)
        self.assertEqual(mandat_fuer_ev(ev2), einheitenmandat)  # R2: Einheit schlägt Sammel
        self.assertEqual(mandat_fuer_ev(self.ev), sammel)
        sammel.refresh_from_db()
        self.assertEqual(sammel.iban, IBAN_B)

    def test_aenderung_sammelmandat_in_place(self):
        mandat = self.sammelmandat(referenz='M2024-090', iban=IBAN_B, bic='BYLADEM1001')
        self.person.sepa_mandat = mandat
        self.person.ibans = [IBAN_B]
        self.person.save(update_fields=['sepa_mandat', 'ibans'])

        antwort = self.anfordern_und_bestaetigen(iban=IBAN_A, bic='COBADEFFXXX')

        self.assertEqual(antwort.status_code, status.HTTP_200_OK, antwort.data)
        self.assertEqual(antwort.data['aktion'], 'aendern')
        self.assertEqual(SEPAMandat.objects.count(), 1)
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_A)
        self.assertEqual(mandat.bic, 'COBADEFFXXX')
        self.assertEqual(mandat.mandatsreferenz, 'M2024-090')
        self.assertEqual(mandat.unterzeichnet_am, date(2022, 3, 1))
        self.assertEqual(mandat.quelle, SEPAMandat.QUELLE_VERWALTUNG)

        self.person.refresh_from_db()
        self.assertEqual(self.person.ibans, [IBAN_A, IBAN_B])  # alte IBAN bleibt erhalten

        eintrag = self.alle_eintraege('sepa_mandat').get()
        self.assertEqual(eintrag.alter_wert, 'M2024-090 DE02 **** **** **** **20 51')
        self.assertIn('DE89 **** **** **** **30 00', eintrag.neuer_wert)
        self.assertEqual(eintrag.quelle, 'Portal-Magic-Link')
        self.assertEqual(mail.outbox[1].subject, 'Ihr SEPA-Lastschriftmandat wurde geändert')

    def test_aenderung_legacy_mandat_ohne_person(self):
        mandat = erstelle_mandat(self.person, referenz='LEGACY-1', iban=IBAN_B)
        self.anfordern_und_bestaetigen()
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_A)
        self.assertEqual(mandat.mandatsreferenz, 'LEGACY-1')
        self.assertEqual(SEPAMandat.objects.count(), 1)

    def test_aenderung_einheitenmandat(self):
        mandat = SEPAMandat.objects.create(
            mandatsreferenz='EV-1', iban=IBAN_B, unterzeichnet_am=date(2022, 1, 1),
            person=self.person, eigentumsverhaeltnis=self.ev,
        )
        self.anfordern_und_bestaetigen(schluessel=f'ev:{self.ev.id}')
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_A)
        self.assertEqual(SEPAMandat.objects.count(), 1)

    def test_bestaetigungsmail_fehler_macht_das_mandat_nicht_ungueltig(self):
        self.anfordern()
        token = self.letzter_token()
        with umock.patch.object(
            mail_service, 'versende_sepa_mandat_bestaetigung', side_effect=RuntimeError('SMTP'),
        ):
            antwort = self.bestaetigen(token)
        self.assertEqual(antwort.status_code, status.HTTP_200_OK)
        self.assertEqual(SEPAMandat.objects.count(), 1)

    def test_nach_bestaetigung_und_aenderung_lauft_der_bankverbindungsweg_ohne_mandat(self):
        """K2 zusammen mit dem neuen Flow: PATCH Bankverbindung ändert das Portal-Mandat nicht."""
        self.anfordern_und_bestaetigen()
        mandat = SEPAMandat.objects.get()
        self.client.patch(BANK_URL, {'iban': IBAN_B})
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_A)


# ---------------------------------------------------------------------------
# Bestätigen: Abweisung — in allen Fällen wird kein Mandat angelegt/geändert
# ---------------------------------------------------------------------------

class SepaBestaetigenAbweisungTest(SepaTestBasis):
    def test_token_ist_einmalig(self):
        self.anfordern()
        token = self.letzter_token()
        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_200_OK)

        zweite = self.bestaetigen(token)

        self.assertEqual(zweite.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)  # keine zweite Bestätigungsmail

    def test_abgelaufener_token(self):
        self.anfordern()
        token = self.letzter_token()
        PortalToken.objects.filter(token=token).update(gueltig_bis=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)

    def test_falscher_token_typ(self):
        self.client.post('/api/v1/portal/meine-daten/email/', {'email': 'neu@example.org'})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EMAIL_BESTAETIGUNG)

        self.assertEqual(self.bestaetigen(token.token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)
        token.refresh_from_db()
        self.assertIsNone(token.verbraucht_am)

    def test_unbekannter_token(self):
        self.assertEqual(self.bestaetigen('unbekannt').status_code, status.HTTP_400_BAD_REQUEST)

    def test_ohne_kontoinhaber_erklaerung_bleibt_token_gueltig(self):
        self.anfordern()
        token = self.letzter_token()

        for erklaerung in (False, None):
            antwort = self.anonym.post(
                BESTAETIGEN_URL, {'token': token, 'kontoinhaber_erklaerung': erklaerung},
                format='json',
            )
            self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        ohne_feld = self.anonym.post(BESTAETIGEN_URL, {'token': token}, format='json')
        self.assertEqual(ohne_feld.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Inhaber', ohne_feld.data['detail'])

        self.assertEqual(SEPAMandat.objects.count(), 0)
        self.assertIsNone(PortalToken.objects.get(token=token).verbraucht_am)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_OFFEN)

        # mit Erklärung geht es danach
        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_200_OK)

    def test_oeffnen_der_vorschau_ist_keine_zustimmung(self):
        self.anfordern()
        self.anonym.get(vorschau_url(self.letzter_token()))
        self.assertEqual(SEPAMandat.objects.count(), 0)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_OFFEN)

    def test_zustandskonflikt_sammelmandat_zwischenzeitlich_angelegt(self):
        self.anfordern()
        token = self.letzter_token()
        admin_mandat = self.sammelmandat(referenz='ADMIN-1')  # Verwaltung legt zwischendurch an

        antwort = self.bestaetigen(token)

        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('neu an.', antwort.data['detail'])
        antrag = Antrag.objects.get()
        self.assertEqual(antrag.status, Antrag.STATUS_VERWORFEN)
        self.assertIn('bereits ein SEPA-Mandat', antrag.verworfen_grund)
        self.assertEqual(SEPAMandat.objects.get(), admin_mandat)
        admin_mandat.refresh_from_db()
        self.assertEqual(admin_mandat.iban, IBAN_B)
        self.assertEqual(self.alle_eintraege('sepa_mandat').count(), 0)
        self.assertEqual(len(mail.outbox), 1)  # nur die Link-Mail
        # der Link ist danach endgültig tot
        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)

    def test_zustandskonflikt_einheitenmandat_zwischenzeitlich_angelegt(self):
        ev2 = self.zweite_einheit()
        self.anfordern(schluessel=f'ev:{ev2.id}')
        token = self.letzter_token()
        SEPAMandat.objects.create(
            mandatsreferenz='ADMIN-EV', iban=IBAN_B, unterzeichnet_am=date(2022, 1, 1),
            person=self.person, eigentumsverhaeltnis=ev2,
        )

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 1)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_VERWORFEN)

    def test_ev_zwischenzeitlich_beendet(self):
        ev2 = self.zweite_einheit()
        self.anfordern(schluessel=f'ev:{ev2.id}')
        token = self.letzter_token()
        ev2.ende = date(2024, 1, 31)
        ev2.save(update_fields=['ende'])

        antwort = self.bestaetigen(token)

        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)
        antrag = Antrag.objects.get()
        self.assertEqual(antrag.status, Antrag.STATUS_VERWORFEN)
        self.assertIn('nicht mehr', antrag.verworfen_grund)

    def test_sammelmandat_alle_einheiten_beendet(self):
        self.anfordern()
        token = self.letzter_token()
        self.ev.ende = date(2024, 1, 31)
        self.ev.save(update_fields=['ende'])

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_VERWORFEN)

    def test_glaeubiger_hat_sich_geaendert(self):
        self.anfordern()
        token = self.letzter_token()
        self.objekt.glaeubiger_id = 'DE00ZZZ00000000000'
        self.objekt.save(update_fields=['glaeubiger_id'])

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_VERWORFEN)

    def test_neue_einheit_in_anderem_weg_aendert_den_text_des_sammelmandats(self):
        self.anfordern()
        token = self.letzter_token()
        self.zweite_einheit()  # neuer Gläubiger, dem der Eigentümer nicht zugestimmt hat

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)

    def test_aenderung_ziel_mandat_zwischenzeitlich_deaktiviert(self):
        mandat = self.sammelmandat()
        self.anfordern()
        token = self.letzter_token()
        mandat.aktiv = False
        mandat.save(update_fields=['aktiv'])

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_B)
        self.assertEqual(SEPAMandat.objects.count(), 1)
        self.assertEqual(Antrag.objects.get().status, Antrag.STATUS_VERWORFEN)

    def test_aenderung_mandat_zwischenzeitlich_geteilt(self):
        mandat = self.sammelmandat()
        self.person.sepa_mandat = mandat
        self.person.save(update_fields=['sepa_mandat'])
        self.anfordern()
        token = self.letzter_token()
        partner = erstelle_eigentuemer(
            nachname='Partner', email='partner@example.org', personennummer='P-PORTAL-9',
        )
        partner.sepa_mandat = mandat
        partner.save(update_fields=['sepa_mandat'])

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, IBAN_B)

    def test_gesperrter_zugang(self):
        self.anfordern()
        token = self.letzter_token()
        self.zugang.aktiv = False
        self.zugang.save(update_fields=['aktiv'])

        self.assertEqual(self.bestaetigen(token).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SEPAMandat.objects.count(), 0)

    def test_referenz_inzwischen_vergeben_wird_nicht_still_neu_nummeriert(self):
        self.anfordern()
        antrag = Antrag.objects.get()
        # Fremdes Mandat mit genau dieser Referenz, aber für eine andere Person
        andere = erstelle_eigentuemer(
            nachname='Andere', email='andere@example.org', personennummer='P-PORTAL-8',
        )
        SEPAMandat.objects.create(
            mandatsreferenz=antrag.mandatsreferenz, iban=IBAN_B,
            unterzeichnet_am=date(2022, 1, 1), person=andere,
        )

        antwort = self.bestaetigen(self.letzter_token())

        self.assertEqual(antwort.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('neu an.', antwort.data['detail'])
        self.assertEqual(SEPAMandat.objects.count(), 1)
        antrag.refresh_from_db()
        self.assertEqual(antrag.status, Antrag.STATUS_VERWORFEN)

    def test_bestaetigen_ist_ohne_sitzung_erreichbar_aber_gethrottelt_scope_portal_auth(self):
        # Kein Portal-Header nötig; ein Fremder mit geratenem Token scheitert.
        self.assertEqual(
            self.anonym.post(
                BESTAETIGEN_URL, {'token': 'x' * 64, 'kontoinhaber_erklaerung': True}, format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

class HilfsfunktionenTest(SimpleTestCase):
    def test_maskiere_iban(self):
        self.assertEqual(maskiere_iban(IBAN_A), 'DE89 **** **** **** **30 00')
        self.assertEqual(maskiere_iban('DE89 3704 0044 0532 0130 00'), 'DE89 **** **** **** **30 00')
        self.assertEqual(maskiere_iban('DE89'), 'DE89')

    def test_pruefe_iban(self):
        self.assertTrue(pruefe_iban(IBAN_A)['valid'])
        self.assertEqual(pruefe_iban('DE89 3704 0044 0532 0130 00')['iban'], IBAN_A)
        self.assertEqual(pruefe_iban('DE89370400440532013001'), {
            'valid': False, 'error': 'Diese IBAN ist ungültig.',
        })
        self.assertFalse(pruefe_iban('')['valid'])

    def test_normalisiere_iban(self):
        self.assertEqual(normalisiere_iban(' de89 3704 0044 0532 0130 00 '), IBAN_A)

    def test_client_ip_reihenfolge(self):
        rf = RequestFactory()
        r = rf.get('/', HTTP_X_REAL_IP='1.1.1.1', HTTP_X_FORWARDED_FOR='2.2.2.2, 3.3.3.3',
                   REMOTE_ADDR='4.4.4.4')
        self.assertEqual(client_ip(r), ('1.1.1.1', '2.2.2.2, 3.3.3.3'))
        r = rf.get('/', HTTP_X_FORWARDED_FOR='2.2.2.2, 3.3.3.3', REMOTE_ADDR='4.4.4.4')
        self.assertEqual(client_ip(r), ('2.2.2.2', '2.2.2.2, 3.3.3.3'))
        r = rf.get('/', REMOTE_ADDR='4.4.4.4')
        self.assertEqual(client_ip(r), ('4.4.4.4', ''))

    def test_client_ip_ungueltiger_wert_wird_uebersprungen(self):
        r = RequestFactory().get('/', HTTP_X_REAL_IP='kaputt', REMOTE_ADDR='4.4.4.4')
        self.assertEqual(client_ip(r), ('4.4.4.4', ''))
        r = RequestFactory().get('/', HTTP_X_REAL_IP='kaputt', REMOTE_ADDR='')
        self.assertEqual(client_ip(r), (None, ''))
