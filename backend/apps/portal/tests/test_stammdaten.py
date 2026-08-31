"""
Tests für die Selbstpflege der Stammdaten (Spec 1a, Kap. 5 und 8).

Deckt die Akzeptanzkriterien ab:
  - je geändertem Feld genau ein Audit-Eintrag
  - Bankverbindung mit aktivem Mandat: Mandat wird aktualisiert,
    Mandatsreferenz bleibt gleich
  - Bankverbindung ohne aktives Mandat: kein Mandat wird berührt
  - E-Mail-Änderung erst nach Bestätigung wirksam, alte Adresse bleibt
    bis dahin login-fähig
"""
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.personen.models import SEPAMandat
from apps.portal.models import PersonStammdatenAenderung, PortalToken
from apps.portal.services import zugang_service
from .basis import erstelle_eigentuemer, erstelle_mandat

DATEN_URL = '/api/v1/portal/meine-daten/'
BANK_URL = '/api/v1/portal/meine-daten/bankverbindung/'
EMAIL_URL = '/api/v1/portal/meine-daten/email/'
EMAIL_BESTAETIGEN_URL = '/api/v1/portal/meine-daten/email/bestaetigen/'
REQUEST_URL = '/api/v1/portal/auth/magic-link/request/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalTestBasis(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.person = erstelle_eigentuemer(email='alt@example.org')
        self.zugang, token = zugang_service.lade_ein(self.person)
        self.session, _ = zugang_service.melde_an(token.token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Portal {self.session.token}')

    def eintraege(self, feld):
        return PersonStammdatenAenderung.objects.filter(person=self.person, feld=feld)


class KontaktAenderungTest(PortalTestBasis):
    def test_get_liefert_eigene_stammdaten(self):
        response = self.client.get(DATEN_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'alt@example.org')
        self.assertEqual(response.data['telefon'], '0123 4567')
        self.assertEqual(response.data['strasse'], 'Altstraße')
        self.assertEqual(response.data['hausnummer'], '1')
        self.assertEqual(response.data['plz'], '12345')
        self.assertEqual(response.data['ort'], 'Altstadt')

    def test_adressaenderung_erzeugt_genau_einen_audit_eintrag_je_feld(self):
        response = self.client.patch(DATEN_URL, {'strasse': 'Neuweg', 'hausnummer': '9'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.person.refresh_from_db()
        self.assertEqual(self.person.strasse, 'Neuweg')
        self.assertEqual(self.person.hausnummer, '9')

        eintraege = self.eintraege('strasse')
        self.assertEqual(eintraege.count(), 1)
        eintrag = eintraege.first()
        self.assertEqual(eintrag.alter_wert, 'Altstraße')
        self.assertEqual(eintrag.neuer_wert, 'Neuweg')
        self.assertEqual(eintrag.quelle, PersonStammdatenAenderung.QUELLE_PORTAL)
        self.assertEqual(self.eintraege('hausnummer').count(), 1)

    def test_adress_textblock_wird_mitgefuehrt(self):
        """``Person.adresse`` wird von Anschreiben-PDF und EV-Postversand
        weiterhin direkt gelesen — er muss den Einzelfeldern folgen."""
        self.client.patch(DATEN_URL, {
            'strasse': 'Neuweg', 'hausnummer': '9', 'plz': '54321', 'ort': 'Neustadt',
        })
        self.person.refresh_from_db()
        self.assertEqual(self.person.adresse, 'Neuweg 9\n54321 Neustadt')

    def test_alle_adressfelder_und_telefon_erzeugen_je_einen_eintrag(self):
        """Spec Kap. 4.2: ein Eintrag JE FELD, keine Sammelbuchung."""
        self.client.patch(DATEN_URL, {
            'strasse': 'Neuweg', 'hausnummer': '9', 'plz': '54321',
            'ort': 'Neustadt', 'telefon': '0999 111',
        })
        for feld in ('strasse', 'hausnummer', 'plz', 'ort', 'telefon'):
            self.assertEqual(self.eintraege(feld).count(), 1, f'Feld {feld}')

    def test_unveraenderter_wert_erzeugt_keinen_eintrag(self):
        self.client.patch(DATEN_URL, {'strasse': self.person.strasse})
        self.assertEqual(self.eintraege('strasse').count(), 0)

    def test_ungueltige_plz_wird_abgelehnt(self):
        response = self.client.patch(DATEN_URL, {'plz': 'ABC'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.person.refresh_from_db()
        self.assertEqual(self.person.plz, '12345')

    def test_adress_textblock_ist_nicht_direkt_beschreibbar(self):
        """Sonst würden Textblock und Einzelfelder auseinanderlaufen."""
        self.client.patch(DATEN_URL, {'adresse': 'Manipuliert 1\n99999 Nirgendwo'})
        self.person.refresh_from_db()
        self.assertEqual(self.person.adresse, 'Altstraße 1\n12345 Altstadt')

    def test_telefon_wird_auch_in_der_json_liste_aktualisiert(self):
        """Sonst liefert die Leselogik (JSON zuerst) weiter die alte Nummer."""
        self.client.patch(DATEN_URL, {'telefon': '0999 111'})
        self.person.refresh_from_db()
        self.assertEqual(self.person.telefon, '0999 111')
        self.assertEqual(self.person.telefonnummern[0], '0999 111')

    def test_name_ist_nicht_aenderbar(self):
        """Identitätsrelevante Stammdaten bleiben Verwaltungssache (Kap. 1.2)."""
        self.client.patch(DATEN_URL, {'nachname': 'Fälschung', 'strasse': 'Neuweg'})
        self.person.refresh_from_db()
        self.assertEqual(self.person.nachname, 'Musterfrau')

    def test_leerer_patch_wird_abgelehnt(self):
        response = self.client.patch(DATEN_URL, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BankverbindungMitMandatTest(PortalTestBasis):
    def setUp(self):
        super().setUp()
        self.mandat = erstelle_mandat(self.person)

    def test_mandat_wird_aktualisiert_referenz_bleibt_gleich(self):
        """Akzeptanzkriterium Kap. 8: Mandat direkt aktualisiert,
        Mandatsreferenz unverändert."""
        neue_iban = 'DE89370400440532013000'
        response = self.client.patch(BANK_URL, {'iban': neue_iban})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['mandat_aktualisiert'])

        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.iban, neue_iban)
        self.assertEqual(self.mandat.mandatsreferenz, 'MND-PORTAL-1')
        self.assertEqual(SEPAMandat.objects.count(), 1)

    def test_audit_eintrag_fuer_iban_und_mandatsbezug(self):
        self.client.patch(BANK_URL, {'iban': 'DE89370400440532013000'})

        self.assertEqual(self.eintraege('iban').count(), 1)
        mandat_eintrag = self.eintraege('sepa_mandat').first()
        self.assertIsNotNone(mandat_eintrag)
        self.assertIn('MND-PORTAL-1', mandat_eintrag.neuer_wert)
        self.assertIn('unverändert', mandat_eintrag.neuer_wert)

    def test_alte_iban_bleibt_in_der_personenliste_erhalten(self):
        """Die E-Banking-Erkennung ordnet Zahlungen über Person.ibans zu."""
        alt = self.person.ibans[0]
        self.client.patch(BANK_URL, {'iban': 'DE89370400440532013000'})

        self.person.refresh_from_db()
        self.assertEqual(self.person.ibans[0], 'DE89370400440532013000')
        self.assertIn(alt, self.person.ibans)

    def test_iban_mit_leerzeichen_wird_normalisiert(self):
        self.client.patch(BANK_URL, {'iban': 'DE89 3704 0044 0532 0130 00'})
        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.iban, 'DE89370400440532013000')

    def test_ungueltige_iban_wird_abgelehnt(self):
        response = self.client.patch(BANK_URL, {'iban': 'DE00KEINEIBAN'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.iban, 'DE02120300000000202051')

    def test_bic_aenderung_landet_im_mandat(self):
        self.client.patch(BANK_URL, {'bic': 'COBADEFFXXX'})
        self.mandat.refresh_from_db()
        self.assertEqual(self.mandat.bic, 'COBADEFFXXX')
        self.assertEqual(self.eintraege('bic').count(), 1)

    def test_unveraenderte_iban_erzeugt_keinen_eintrag(self):
        self.client.patch(BANK_URL, {'iban': self.mandat.iban})
        self.assertEqual(self.eintraege('iban').count(), 0)

    def test_hinweis_auf_mandat_wird_ausgeliefert(self):
        """Transparenz für den Eigentümer (Spec Kap. 6.2)."""
        response = self.client.get(DATEN_URL)
        self.assertTrue(response.data['hat_aktives_mandat'])
        self.assertEqual(response.data['mandatsreferenz'], 'MND-PORTAL-1')


class BankverbindungOhneMandatTest(PortalTestBasis):
    def test_ohne_mandat_wird_nur_die_person_geaendert(self):
        """Akzeptanzkriterium Kap. 8: kein Mandat wird berührt."""
        response = self.client.patch(BANK_URL, {'iban': 'DE89370400440532013000'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['mandat_aktualisiert'])
        self.assertEqual(SEPAMandat.objects.count(), 0)

        self.person.refresh_from_db()
        self.assertEqual(self.person.ibans[0], 'DE89370400440532013000')
        self.assertEqual(self.eintraege('iban').count(), 1)

    def test_inaktives_mandat_wird_nicht_angefasst(self):
        mandat = erstelle_mandat(self.person, referenz='MND-INAKTIV', aktiv=False)
        alte_iban = mandat.iban

        self.client.patch(BANK_URL, {'iban': 'DE89370400440532013000'})

        mandat.refresh_from_db()
        self.assertEqual(mandat.iban, alte_iban)


class EmailAenderungTest(PortalTestBasis):
    def test_aenderung_ist_erst_nach_bestaetigung_wirksam(self):
        """Akzeptanzkriterium Kap. 8, E-Mail-Flow."""
        response = self.client.post(EMAIL_URL, {'email': 'neu@example.org'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.zugang.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(self.zugang.email_pending, 'neu@example.org')
        self.assertEqual(self.person.email, 'alt@example.org')
        self.assertEqual(self.eintraege('email').count(), 0)

    def test_bestaetigungsmail_geht_an_die_neue_adresse(self):
        self.client.post(EMAIL_URL, {'email': 'neu@example.org'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['neu@example.org'])

    def test_alte_adresse_bleibt_bis_zur_bestaetigung_login_faehig(self):
        self.client.post(EMAIL_URL, {'email': 'neu@example.org'})

        self.assertIsNotNone(zugang_service.finde_zugang_per_email('alt@example.org'))
        self.assertIsNone(zugang_service.finde_zugang_per_email('neu@example.org'))

    def test_bestaetigung_uebernimmt_die_neue_adresse(self):
        self.client.post(EMAIL_URL, {'email': 'neu@example.org'})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EMAIL_BESTAETIGUNG)

        # Bewusst ohne Portal-Sitzung: der Link wird typischerweise im
        # neuen Postfach geöffnet, oft in einem anderen Browser.
        self.client.credentials()
        response = self.client.post(EMAIL_BESTAETIGEN_URL, {'token': token.token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.person.refresh_from_db()
        self.zugang.refresh_from_db()
        self.assertEqual(self.person.email, 'neu@example.org')
        self.assertEqual(self.person.emails[0], 'neu@example.org')
        self.assertEqual(self.zugang.email_pending, '')
        self.assertEqual(self.eintraege('email').count(), 1)

    def test_login_funktioniert_nach_bestaetigung_mit_der_neuen_adresse(self):
        self.client.post(EMAIL_URL, {'email': 'neu@example.org'})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EMAIL_BESTAETIGUNG)
        self.client.credentials()
        self.client.post(EMAIL_BESTAETIGEN_URL, {'token': token.token})

        self.assertIsNotNone(zugang_service.finde_zugang_per_email('neu@example.org'))
        self.assertIsNone(zugang_service.finde_zugang_per_email('alt@example.org'))

    def test_bestaetigungslink_ist_einmalig(self):
        self.client.post(EMAIL_URL, {'email': 'neu@example.org'})
        token = PortalToken.objects.get(typ=PortalToken.TYP_EMAIL_BESTAETIGUNG)
        self.client.credentials()

        erste = self.client.post(EMAIL_BESTAETIGEN_URL, {'token': token.token})
        self.assertEqual(erste.status_code, status.HTTP_200_OK)

        zweite = self.client.post(EMAIL_BESTAETIGEN_URL, {'token': token.token})
        self.assertEqual(zweite.status_code, status.HTTP_400_BAD_REQUEST)

    def test_spaetere_aenderung_lenkt_einen_versendeten_link_nicht_um(self):
        """``ziel_email`` am Token, nicht ``email_pending`` am Zugang."""
        self.client.post(EMAIL_URL, {'email': 'erste@example.org'})
        erster_token = PortalToken.objects.get(
            typ=PortalToken.TYP_EMAIL_BESTAETIGUNG, ziel_email='erste@example.org',
        )
        self.client.post(EMAIL_URL, {'email': 'zweite@example.org'})

        erster_token.refresh_from_db()
        self.assertIsNotNone(
            erster_token.verbraucht_am,
            'Der erste Bestätigungslink muss beim Nachfordern entwertet werden.',
        )

    def test_bereits_hinterlegte_adresse_wird_abgelehnt(self):
        response = self.client.post(EMAIL_URL, {'email': 'alt@example.org'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_adresse_eines_anderen_zugangs_wird_abgelehnt(self):
        andere = erstelle_eigentuemer(
            nachname='Zweitfrau', email='fremd@example.org',
            personennummer='P-PORTAL-2',
        )
        zugang_service.lade_ein(andere)

        response = self.client.post(EMAIL_URL, {'email': 'fremd@example.org'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.zugang.refresh_from_db()
        self.assertEqual(self.zugang.email_pending, '')
