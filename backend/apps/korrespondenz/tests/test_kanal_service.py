"""Test 16 (Teil 1): Kanal-Auflösung inkl. "Mahnstufe 3 immer auch Brief" - reine Logik."""
from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.korrespondenz.services import kanal_service

ZUSTIMMUNG = datetime(2026, 1, 1, tzinfo=timezone.utc)


def person(*, zustellweg='email', zustimmung=ZUSTIMMUNG, email='eigentuemer@example.org', emails=None):
    return SimpleNamespace(
        zustellweg=zustellweg, zustellweg_zustimmung_am=zustimmung,
        email=email, emails=emails or [],
    )


def vorlage(kanal_standard='email', anlass='eigentuemer_allgemein'):
    return SimpleNamespace(kanal_standard=kanal_standard, anlass=anlass)


class KanalAufloesenTest(SimpleTestCase):

    def test_vorlage_brief_bleibt_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('brief'), person())
        self.assertEqual((erg.kanal, erg.auch_brief), ('brief', False))

    def test_email_mit_zustimmung_und_adresse(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email'), person())
        self.assertEqual((erg.kanal, erg.auch_brief, erg.hinweis), ('email', False, ''))

    def test_zustellweg_post_gibt_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email'), person(zustellweg='post'))
        self.assertEqual(erg.kanal, 'brief')
        self.assertIn('nicht E-Mail', erg.hinweis)

    def test_ohne_zustimmung_gibt_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email'), person(zustimmung=None))
        self.assertEqual(erg.kanal, 'brief')
        self.assertIn('Zustimmung', erg.hinweis)

    def test_ohne_adresse_gibt_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email'), person(email=''))
        self.assertEqual(erg.kanal, 'brief')
        self.assertIn('E-Mail-Adresse', erg.hinweis)

    def test_adresse_aus_emails_liste_string_und_dict(self):
        for emails in (['a@example.org'], [{'adresse': 'a@example.org'}], [{'email': 'a@example.org'}]):
            with self.subTest(emails=emails):
                erg = kanal_service.kanal_aufloesen(vorlage('email'), person(email='', emails=emails))
                self.assertEqual(erg.kanal, 'email')

    def test_beides_mit_zustimmung_ist_email_und_auch_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('beides'), person())
        self.assertEqual((erg.kanal, erg.auch_brief), ('email', True))

    def test_beides_ohne_zustimmung_ist_nur_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('beides'), person(zustimmung=None))
        self.assertEqual((erg.kanal, erg.auch_brief), ('brief', False))

    def test_expliziter_kanal_uebersteuert_vorlage(self):
        self.assertEqual(kanal_service.kanal_aufloesen(vorlage('brief'), person(), kanal='email').kanal, 'email')
        self.assertEqual(kanal_service.kanal_aufloesen(vorlage('email'), person(), kanal='brief').kanal, 'brief')

    def test_unbekannter_kanal(self):
        with self.assertRaises(ValueError):
            kanal_service.kanal_aufloesen(vorlage('email'), person(), kanal='fax')


class MahnstufeDreiTest(SimpleTestCase):
    """Stufe 3 geht IMMER auch als Brief, selbst bei reinem E-Mail-Kanal."""

    def test_stufe_3_ueber_anlass(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email', 'mahnung_stufe_3'), person())
        self.assertEqual((erg.kanal, erg.auch_brief), ('email', True))

    def test_stufe_3_ueber_verknuepfte_mahnung(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email', 'mahnung_stufe_2'), person(), mahnstufe=3)
        self.assertEqual((erg.kanal, erg.auch_brief), ('email', True))

    def test_stufe_1_und_2_nur_email(self):
        for anlass, stufe in (('mahnung_stufe_1', 1), ('mahnung_stufe_2', 2)):
            with self.subTest(anlass=anlass):
                erg = kanal_service.kanal_aufloesen(vorlage('email', anlass), person(), mahnstufe=stufe)
                self.assertEqual((erg.kanal, erg.auch_brief), ('email', False))

    def test_stufe_3_ohne_email_moeglichkeit_ist_brief(self):
        erg = kanal_service.kanal_aufloesen(vorlage('email', 'mahnung_stufe_3'), person(zustimmung=None))
        self.assertEqual(erg.kanal, 'brief')

    def test_braucht_brief_am_schreiben(self):
        def schreiben(kanal, kanal_standard, anlass, mahnstufe=None):
            return SimpleNamespace(
                kanal=kanal, mahnung_id=1 if mahnstufe else None,
                mahnung=SimpleNamespace(mahnstufe=mahnstufe) if mahnstufe else None,
                vorlage_version=SimpleNamespace(vorlage=vorlage(kanal_standard, anlass)),
            )
        self.assertTrue(kanal_service.braucht_brief(schreiben('brief', 'brief', 'eigentuemer_allgemein')))
        self.assertFalse(kanal_service.braucht_brief(schreiben('email', 'email', 'mahnung_stufe_2', 2)))
        self.assertTrue(kanal_service.braucht_brief(schreiben('email', 'email', 'mahnung_stufe_3')))
        self.assertTrue(kanal_service.braucht_brief(schreiben('email', 'email', 'mahnung_stufe_2', 3)))
        self.assertTrue(kanal_service.braucht_brief(schreiben('email', 'beides', 'eigentuemer_allgemein')))


class LetzteMahnstufeTest(SimpleTestCase):
    """Die Brief-Pflicht hängt an der LETZTEN Stufe des Objekts (``MahnEinstellung.anzahl_mahnstufen``)."""

    def test_stufe_2_ist_bei_zwei_stufen_die_letzte(self):
        erg = kanal_service.kanal_aufloesen(
            vorlage('email', 'mahnung_stufe_2'), person(), mahnstufe=2, letzte_stufe=2)
        self.assertEqual((erg.kanal, erg.auch_brief), ('email', True))

    def test_stufe_1_ist_bei_zwei_stufen_nicht_die_letzte(self):
        erg = kanal_service.kanal_aufloesen(
            vorlage('email', 'mahnung_stufe_2'), person(), mahnstufe=1, letzte_stufe=2)
        self.assertEqual((erg.kanal, erg.auch_brief), ('email', False))

    def test_stufe_1_ist_bei_einer_stufe_die_letzte(self):
        erg = kanal_service.kanal_aufloesen(
            vorlage('email', 'mahnung_stufe_2'), person(), mahnstufe=1, letzte_stufe=1)
        self.assertTrue(erg.auch_brief)

    def test_ohne_konfiguration_gilt_stufe_3(self):
        self.assertFalse(kanal_service.ist_letzte_mahnstufe('mahnung_stufe_2', 2, None))
        self.assertTrue(kanal_service.ist_letzte_mahnstufe('mahnung_stufe_2', 3, None))

    def test_letzte_stufe_von_der_mahnung(self):
        def mahnung(anzahl):
            einstellung = SimpleNamespace(anzahl_mahnstufen=anzahl)
            return SimpleNamespace(personenkonto=SimpleNamespace(objekt=SimpleNamespace(mahn_einstellung=einstellung)))
        self.assertEqual(kanal_service.letzte_stufe_von(mahnung(2)), 2)
        self.assertIsNone(kanal_service.letzte_stufe_von(SimpleNamespace(mahnstufe=2)))     # keine Konfiguration
        self.assertIsNone(kanal_service.letzte_stufe_von(None))

    def test_braucht_brief_am_schreiben_bei_letzter_stufe(self):
        def schreiben(anzahl, stufe):
            einstellung = SimpleNamespace(anzahl_mahnstufen=anzahl)
            mahnung = SimpleNamespace(
                mahnstufe=stufe,
                personenkonto=SimpleNamespace(objekt=SimpleNamespace(mahn_einstellung=einstellung)),
            )
            return SimpleNamespace(
                kanal='email', mahnung_id=1, mahnung=mahnung,
                vorlage_version=SimpleNamespace(vorlage=vorlage('email', 'mahnung_stufe_2')),
            )
        self.assertTrue(kanal_service.braucht_brief(schreiben(2, 2)))
        self.assertFalse(kanal_service.braucht_brief(schreiben(2, 1)))
