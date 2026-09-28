"""
Tests für die Aktensichten (Haus-, Wohnungs-, Eigentümerakte).

Schwerpunkt ist die zeitliche Abgrenzung der Eigentümerakte: Nach einem
Verkauf darf der neue Eigentümer den Schriftwechsel des Vorbesitzers nicht
sehen — und umgekehrt. Das ist der Punkt, an dem ein Fehler datenschutz-
rechtlich weh tut, nicht nur kosmetisch.

Ebenfalls abgesichert: der Überschneidungsfall, der den Anlass gab — ein
Eigentümer mit mehreren Wohnungen in verschiedenen Objekten.
"""
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.services import akten_service
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_akten_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class AktenBasis(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='akten-tester', password='x')

        self.objekt_a = Objekt.objects.create(
            bezeichnung='WEG Alpha', objektnummer='AK001', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))
        self.objekt_b = Objekt.objects.create(
            bezeichnung='WEG Beta', objektnummer='AK002', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))

        self.w1 = Einheit.objects.create(
            objekt=self.objekt_a, einheit_nr='W01', einheit_typ='Wohnung', lage='EG')
        self.w2 = Einheit.objects.create(
            objekt=self.objekt_a, einheit_nr='W02', einheit_typ='Wohnung', lage='1. OG')
        self.w3 = Einheit.objects.create(
            objekt=self.objekt_b, einheit_nr='W01', einheit_typ='Wohnung', lage='EG')

        self.verkaeufer = Person.objects.create(
            personennummer='P-AK-V', person_typ='100', vorname='Alt',
            nachname='Verkaeufer')
        self.kaeufer = Person.objects.create(
            personennummer='P-AK-K', person_typ='100', vorname='Neu',
            nachname='Kaeufer')

    def _dokument(self, *, dateiname='akte.pdf', register=None, datum=None,
                  **kontext) -> Dokument:
        from django.core.files.base import ContentFile
        dokument = Dokument(
            datei=ContentFile(b'%PDF-1.4 x', name=dateiname),
            dateiname=dateiname, kategorie='Test', dokument_typ='sonstiges',
            register=register, dokument_datum=datum,
            hochgeladen_von=self.user, **kontext)
        dokument.full_clean()
        dokument.save()
        return dokument


class RegisterTest(AktenBasis):
    # Codes mit TEST-Praefix: die Migration seedet 01-21, ein "04" hier
    # liefe in den Unique-Constraint.
    def test_voller_pfad_zeigt_die_gliederung(self):
        oben = Aktenregister.objects.create(
            code='T04', bezeichnung='Versicherungen', sortierung=40)
        unten = Aktenregister.objects.create(
            code='T04.1', bezeichnung='Gebäude', eltern=oben, sortierung=41)

        self.assertEqual(unten.voller_pfad, 'T04 Versicherungen / T04.1 Gebäude')

    def test_register_darf_keinen_kreis_bilden(self):
        from django.core.exceptions import ValidationError
        a = Aktenregister.objects.create(code='TA', bezeichnung='A')
        b = Aktenregister.objects.create(code='TB', bezeichnung='B', eltern=a)
        a.eltern = b
        with self.assertRaises(ValidationError):
            a.full_clean()


class ObjektspezifischeRegisterTest(AktenBasis):
    """Das digitale Trennblatt: "05/A Hebeanlage" gilt nur in EINEM Haus.

    Der Fall aus der Praxis — Objekt A hat eine Hebeanlage, Objekt B nicht.
    Ein global angelegtes Unterregister stuende in jeder Akte und taeuschte
    ueberall eine Anlage vor, die es nicht gibt.
    """

    def setUp(self):
        super().setUp()
        # Bewusst das geseedete Register: genau daran haengt in der Praxis
        # die Untergliederung.
        self.wartung = Aktenregister.objects.get(code='05', objekt__isnull=True)
        self.hebeanlage = Aktenregister.objects.create(
            code='05/A', bezeichnung='Hebeanlage', sortierung=51,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.objekt_a)

    def test_unterregister_erscheint_nur_im_eigenen_objekt(self):
        codes_a = [g['code'] for g in akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a),
            Aktenregister.AKTENART_HAUS, objekt=self.objekt_a)]
        codes_b = [g['code'] for g in akten_service.nach_registern(
            akten_service.hausakte(self.objekt_b),
            Aktenregister.AKTENART_HAUS, objekt=self.objekt_b)]

        self.assertIn('05/A', codes_a)
        self.assertNotIn('05/A', codes_b)
        # Das gemeinsame Register steht in beiden.
        self.assertIn('05', codes_a)
        self.assertIn('05', codes_b)

    def test_ohne_objekt_bleiben_nur_die_gemeinsamen_register(self):
        codes = [r.code for r in akten_service.register_einer_akte(
            Aktenregister.AKTENART_HAUS)]
        self.assertIn('05', codes)
        self.assertNotIn('05/A', codes)

    def test_derselbe_code_darf_in_zwei_objekten_verschiedenes_heissen(self):
        # In Haus B steht "05/A" fuer den Aufzug — kein Konflikt.
        aufzug = Aktenregister.objects.create(
            code='05/A', bezeichnung='Aufzug', sortierung=51,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.objekt_b)

        self.assertEqual(aufzug.code, self.hebeanlage.code)
        self.assertNotEqual(aufzug.objekt, self.hebeanlage.objekt)

    def test_global_darf_ein_code_nur_einmal_vorkommen(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aktenregister.objects.create(
                code='05', bezeichnung='Doppelt', aktenart=Aktenregister.AKTENART_HAUS)

    def test_unterregister_steht_direkt_hinter_seinem_elternregister(self):
        # "17 Rechtsangelegenheiten" kommt aus dem Seed und steht nach
        # Sortiernummer weit hinter "05".
        codes = [g['code'] for g in akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a),
            Aktenregister.AKTENART_HAUS, objekt=self.objekt_a)]

        # Ohne Baumsortierung stuende "05/A" hinter "17".
        self.assertEqual(codes.index('05/A'), codes.index('05') + 1)
        self.assertLess(codes.index('05/A'), codes.index('17'))

    def test_ebene_und_kennzeichnung_kommen_mit(self):
        gruppen = {g['code']: g for g in akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a),
            Aktenregister.AKTENART_HAUS, objekt=self.objekt_a)}

        self.assertEqual(gruppen['05']['ebene'], 0)
        self.assertEqual(gruppen['05/A']['ebene'], 1)
        self.assertFalse(gruppen['05']['objektspezifisch'])
        self.assertTrue(gruppen['05/A']['objektspezifisch'])

    def test_dokument_landet_im_objektspezifischen_register(self):
        vertrag = self._dokument(dateiname='wartung_hebeanlage.pdf',
                                 objekt=self.objekt_a, register=self.hebeanlage)

        gruppen = {g['code']: g for g in akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a),
            Aktenregister.AKTENART_HAUS, objekt=self.objekt_a)}

        self.assertEqual(gruppen['05/A']['dokumente'], [vertrag])
        self.assertEqual(gruppen['05']['anzahl'], 0)

    def test_unterregister_unter_fremdem_objekt_wird_abgelehnt(self):
        from django.core.exceptions import ValidationError
        fremd = Aktenregister(
            code='05/B', bezeichnung='Fremd', aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.hebeanlage, objekt=self.objekt_b)
        with self.assertRaises(ValidationError):
            fremd.full_clean()


class HausakteTest(AktenBasis):
    def test_sammelt_objekt_einheit_und_vorgang(self):
        EigentumsVerhaeltnis.objects.create(
            person=self.verkaeufer, einheit=self.w1, beginn=date(2020, 1, 1))
        am_objekt = self._dokument(dateiname='teilungserklaerung.pdf',
                                   objekt=self.objekt_a)
        an_einheit = self._dokument(dateiname='kaufvertrag.pdf', einheit=self.w1)
        vorgang = Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code='maengelmeldung'),
            betreff='Heizung', objekt=self.objekt_a, erstellt_von=self.user)
        am_vorgang = self._dokument(dateiname='angebot.pdf', vorgang=vorgang)

        akte = set(akten_service.hausakte(self.objekt_a))

        self.assertEqual(akte, {am_objekt, an_einheit, am_vorgang})

    def test_fremdes_objekt_bleibt_draussen(self):
        self._dokument(dateiname='fremd.pdf', objekt=self.objekt_b)
        self.assertEqual(list(akten_service.hausakte(self.objekt_a)), [])


class EigentuemerakteTest(AktenBasis):
    """Der Kern: Was sieht wer nach einem Verkauf?"""

    def setUp(self):
        super().setUp()
        # Verkäufer: 01.01.2018 bis 30.06.2023, danach der Käufer.
        EigentumsVerhaeltnis.objects.create(
            person=self.verkaeufer, einheit=self.w1,
            beginn=date(2018, 1, 1), ende=date(2023, 6, 30))
        EigentumsVerhaeltnis.objects.create(
            person=self.kaeufer, einheit=self.w1, beginn=date(2023, 7, 1))

        self.aus_verkaeuferzeit = self._dokument(
            dateiname='abrechnung_2020.pdf', einheit=self.w1, datum=date(2020, 3, 15))
        self.aus_kaeuferzeit = self._dokument(
            dateiname='abrechnung_2024.pdf', einheit=self.w1, datum=date(2024, 3, 15))

    def test_verkaeufer_sieht_nur_seine_besitzzeit(self):
        akte = set(akten_service.eigentuemerakte(self.verkaeufer))
        self.assertIn(self.aus_verkaeuferzeit, akte)
        self.assertNotIn(self.aus_kaeuferzeit, akte)

    def test_kaeufer_sieht_die_vorbesitzerpost_nicht(self):
        akte = set(akten_service.eigentuemerakte(self.kaeufer))
        self.assertIn(self.aus_kaeuferzeit, akte)
        self.assertNotIn(self.aus_verkaeuferzeit, akte)

    def test_persoenliche_dokumente_bleiben_zeitunabhaengig(self):
        # Ein SEPA-Mandat hängt an der Person, nicht an der Wohnung — es
        # verschwindet nicht, wenn die Wohnung verkauft wird.
        mandat = self._dokument(dateiname='sepa.pdf', person=self.verkaeufer,
                                datum=date(2030, 1, 1))
        self.assertIn(mandat, set(akten_service.eigentuemerakte(self.verkaeufer)))

    def test_ohne_fachliches_datum_zaehlt_das_ablagedatum(self):
        # Fallback-Pfad: heute abgelegt, kein Dokumentdatum -> faellt in die
        # laufende Besitzzeit des Kaeufers.
        ohne_datum = self._dokument(dateiname='ohnedatum.pdf', einheit=self.w1)

        self.assertIn(ohne_datum, set(akten_service.eigentuemerakte(self.kaeufer)))
        self.assertNotIn(ohne_datum, set(akten_service.eigentuemerakte(self.verkaeufer)))

    def test_vorgangsdokumente_bleiben_beim_ausloeser(self):
        vorgang = Vorgang.objects.create(
            typ=VorgangTyp.objects.get(code='maengelmeldung'),
            betreff='Meldung', person=self.verkaeufer, erstellt_von=self.user)
        dokument = self._dokument(dateiname='meldung.pdf', vorgang=vorgang)

        self.assertIn(dokument, set(akten_service.eigentuemerakte(self.verkaeufer)))
        self.assertNotIn(dokument, set(akten_service.eigentuemerakte(self.kaeufer)))

    def test_mehrere_wohnungen_in_verschiedenen_objekten(self):
        # Der Fall, der den Anlass gab: eine Akte fuehrt Dokumente aus
        # mehreren Objekten zusammen.
        EigentumsVerhaeltnis.objects.create(
            person=self.kaeufer, einheit=self.w2, beginn=date(2023, 7, 1))
        EigentumsVerhaeltnis.objects.create(
            person=self.kaeufer, einheit=self.w3, beginn=date(2023, 7, 1))
        aus_a = self._dokument(dateiname='a.pdf', einheit=self.w2,
                               datum=date(2024, 1, 1))
        aus_b = self._dokument(dateiname='b.pdf', einheit=self.w3,
                               datum=date(2024, 1, 1))

        akte = set(akten_service.eigentuemerakte(self.kaeufer))

        self.assertIn(aus_a, akte)
        self.assertIn(aus_b, akte)
        # Dieselben Dokumente stehen weiterhin in ihren Hausakten — die Akte
        # ist eine Sicht, kein Umzug.
        self.assertIn(aus_a, set(akten_service.hausakte(self.objekt_a)))
        self.assertIn(aus_b, set(akten_service.hausakte(self.objekt_b)))

    def test_nur_aktuelle_evs_blendet_verkaufte_wohnungen_aus(self):
        akte = set(akten_service.eigentuemerakte(
            self.verkaeufer, nur_aktuelle_evs=True))
        self.assertNotIn(self.aus_verkaeuferzeit, akte)


class NachRegisternTest(AktenBasis):
    """Gruppierung bei kontrollierter Registermenge.

    Der Seed (01-21) wird hier bewusst geleert: Die Zusicherungen betreffen
    das Verhalten der Gruppierung, nicht den Inhalt der Gliederung — mit 21
    zusaetzlichen Gruppen waeren sie nicht mehr aussagekraeftig. Innerhalb
    der Testtransaktion bleibt das folgenlos.
    """

    def setUp(self):
        super().setUp()
        Aktenregister.objects.all().delete()
        self.r_stamm = Aktenregister.objects.create(
            code='01', bezeichnung='Stammdaten', sortierung=10,
            aktenart=Aktenregister.AKTENART_HAUS)
        self.r_vers = Aktenregister.objects.create(
            code='02', bezeichnung='Versicherungen', sortierung=20,
            aktenart=Aktenregister.AKTENART_HAUS)
        self.r_alle = Aktenregister.objects.create(
            code='99', bezeichnung='Schriftwechsel', sortierung=99,
            aktenart=Aktenregister.AKTENART_ALLE)

    def test_gruppiert_in_gepflegter_reihenfolge(self):
        self._dokument(dateiname='te.pdf', objekt=self.objekt_a, register=self.r_stamm)

        gruppen = akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a), Aktenregister.AKTENART_HAUS,
            objekt=self.objekt_a)

        self.assertEqual([g['code'] for g in gruppen], ['01', '02', '99'])
        self.assertEqual(gruppen[0]['anzahl'], 1)

    def test_leere_register_bleiben_sichtbar(self):
        # Eine Akte ohne die Zeile "Versicherungen" sähe aus wie eine Akte
        # ohne Versicherungsbedarf — leere Register zeigen, wo etwas fehlt.
        gruppen = akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a), Aktenregister.AKTENART_HAUS,
            objekt=self.objekt_a)
        self.assertEqual([g['anzahl'] for g in gruppen], [0, 0, 0])

    def test_register_der_aktenart_alle_erscheint_mit(self):
        self._dokument(dateiname='brief.pdf', objekt=self.objekt_a, register=self.r_alle)
        gruppen = akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a), Aktenregister.AKTENART_HAUS,
            objekt=self.objekt_a)
        schriftwechsel = next(g for g in gruppen if g['code'] == '99')
        self.assertEqual(schriftwechsel['anzahl'], 1)

    def test_nicht_einsortierte_dokumente_gehen_nicht_verloren(self):
        ohne = self._dokument(dateiname='unsortiert.pdf', objekt=self.objekt_a)

        gruppen = akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a), Aktenregister.AKTENART_HAUS,
            objekt=self.objekt_a)

        letzte = gruppen[-1]
        self.assertEqual(letzte['bezeichnung'], akten_service.OHNE_REGISTER)
        self.assertEqual(letzte['dokumente'], [ohne])

    def test_register_einer_anderen_aktenart_landet_unter_ohne_register(self):
        nur_wohnung = Aktenregister.objects.create(
            code='W1', bezeichnung='Mietvertrag', sortierung=5,
            aktenart=Aktenregister.AKTENART_WOHNUNG)
        fremd = self._dokument(dateiname='mv.pdf', objekt=self.objekt_a,
                               register=nur_wohnung)

        gruppen = akten_service.nach_registern(
            akten_service.hausakte(self.objekt_a), Aktenregister.AKTENART_HAUS,
            objekt=self.objekt_a)

        self.assertNotIn('W1', [g['code'] for g in gruppen])
        self.assertIn(fremd, gruppen[-1]['dokumente'])
