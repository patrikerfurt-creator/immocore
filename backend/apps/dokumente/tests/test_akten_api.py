"""
Tests für die Akten-API.

Zwei Zusicherungen stechen heraus:

- Leere Register kommen MIT. Sie sind der Grund, warum man an einer Akte
  sieht, was fehlt — verschwänden sie, sähe eine Akte ohne Versicherung aus
  wie eine ohne Versicherungsbedarf.
- Ein Dokument lässt sich nicht in das Register eines fremden Objekts
  einsortieren. Es wäre danach in keiner Akte auffindbar, ohne dass jemand
  etwas davon merkt.
"""
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.dokumente.models import Aktenregister, Dokument
from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.rechnungen.models import Kreditor, Rechnung

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_aktenapi_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class AktenApiBasis(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='akten-api', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.objekt = Objekt.objects.create(
            bezeichnung='WEG API-Test', objektnummer='API01', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))
        self.fremdes = Objekt.objects.create(
            bezeichnung='WEG Fremd', objektnummer='API02', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))
        self.einheit = Einheit.objects.create(
            objekt=self.objekt, einheit_nr='W01', einheit_typ='Wohnung', lage='EG')

        self.wartung = Aktenregister.objects.get(code='05', objekt__isnull=True)

    def _dokument(self, dateiname='beleg.pdf', register=None, **kontext):
        dokument = Dokument(
            datei=ContentFile(b'%PDF-1.4 x', name=dateiname),
            dateiname=dateiname, kategorie='Test', dokument_typ='sonstiges',
            register=register, hochgeladen_von=self.user, **kontext)
        dokument.full_clean()
        dokument.save()
        return dokument


class HausakteApiTest(AktenApiBasis):
    def test_liefert_alle_einundzwanzig_register(self):
        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['titel'], 'WEG API-Test')
        codes = [r['code'] for r in antwort.data['register']]
        self.assertEqual(codes, [f'{n:02d}' for n in range(1, 22)])

    def test_leere_register_bleiben_in_der_ausgabe(self):
        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})
        self.assertTrue(all(r['anzahl'] == 0 for r in antwort.data['register']))
        self.assertEqual(antwort.data['anzahl_dokumente'], 0)

    def test_dokument_erscheint_in_seinem_register(self):
        self._dokument('wartungsvertrag.pdf', register=self.wartung,
                       objekt=self.objekt)

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        gruppe = next(r for r in antwort.data['register'] if r['code'] == '05')
        self.assertEqual(gruppe['anzahl'], 1)
        self.assertEqual(gruppe['dokumente'][0]['dateiname'], 'wartungsvertrag.pdf')
        self.assertEqual(antwort.data['anzahl_dokumente'], 1)

    def test_nicht_einsortiertes_dokument_landet_unter_ohne_register(self):
        self._dokument('unsortiert.pdf', objekt=self.objekt)

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        letzte = antwort.data['register'][-1]
        self.assertEqual(letzte['bezeichnung'], 'Ohne Register')
        self.assertIsNone(letzte['register_id'])

    def _beleg(self, dateiname, register=None):
        """Kontextloser Rechnungsbeleg (Owner ist die Rechnung)."""
        beleg = Dokument.objects.create(
            datei=ContentFile(b'%PDF-1.4 x', name=dateiname),
            dateiname=dateiname, kategorie='Beleg', dokument_typ='beleg',
            register=register, hochgeladen_von=self.user)
        Rechnung.objects.create(objekt=self.objekt, beleg_dokument=beleg)
        return beleg

    def test_unsortierter_rechnungsbeleg_nicht_in_ohne_register(self):
        # Belege gehoeren in die Kreditorenakte; unsortiert sollen sie die
        # Arbeitsliste der Hausakte nicht zudecken.
        self._beleg('beleg.pdf')
        self._dokument('echte_mail.pdf', objekt=self.objekt)

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        ohne = next(r for r in antwort.data['register']
                    if r['bezeichnung'] == 'Ohne Register')
        namen = [d['dateiname'] for d in ohne['dokumente']]
        self.assertIn('echte_mail.pdf', namen)
        self.assertNotIn('beleg.pdf', namen)

    def test_einsortierter_rechnungsbeleg_bleibt_im_register(self):
        # Wer einen Beleg bewusst in ein Register legt, soll ihn dort behalten.
        self._beleg('beleg_sortiert.pdf', register=self.wartung)

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        gruppe = next(r for r in antwort.data['register'] if r['code'] == '05')
        self.assertEqual([d['dateiname'] for d in gruppe['dokumente']],
                         ['beleg_sortiert.pdf'])

    def test_herkunft_zeigt_den_weg_in_die_akte(self):
        # Ohne diese Angabe wirkt die Hausakte wie ein Sammelsurium: man
        # sieht nicht, ob ein Beleg am Objekt oder an einer Wohnung hängt.
        self._dokument('kaufvertrag.pdf', register=self.wartung,
                       einheit=self.einheit)

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        gruppe = next(r for r in antwort.data['register'] if r['code'] == '05')
        self.assertEqual(gruppe['dokumente'][0]['herkunft'], 'Einheit W01')

    def test_objektspezifisches_register_erscheint_nur_hier(self):
        Aktenregister.objects.create(
            code='05/A', bezeichnung='Hebeanlage', sortierung=51,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.objekt)

        eigen = self.client.get('/api/v1/akten/hausakte/',
                                {'objekt': str(self.objekt.id)})
        fremd = self.client.get('/api/v1/akten/hausakte/',
                                {'objekt': str(self.fremdes.id)})

        eigene_gruppe = next(r for r in eigen.data['register'] if r['code'] == '05/A')
        self.assertTrue(eigene_gruppe['objektspezifisch'])
        self.assertEqual(eigene_gruppe['ebene'], 1)
        self.assertNotIn('05/A', [r['code'] for r in fremd.data['register']])

    def test_ohne_objekt_parameter_kommt_400(self):
        self.assertEqual(self.client.get('/api/v1/akten/hausakte/').status_code, 400)

    def test_ohne_anmeldung_kein_zugriff(self):
        self.client.force_authenticate(None)
        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})
        self.assertEqual(antwort.status_code, 401)


class WohnungsUndEigentuemerakteApiTest(AktenApiBasis):
    def test_wohnungsakte_zeigt_nur_ihre_register(self):
        antwort = self.client.get('/api/v1/akten/wohnungsakte/',
                                  {'einheit': str(self.einheit.id)})

        self.assertEqual(antwort.status_code, 200)
        # Nur "21 Schriftwechsel" hat aktenart='alle'; eigene
        # Wohnungsakten-Register gibt es noch nicht.
        self.assertEqual([r['code'] for r in antwort.data['register']], ['21'])

    def test_eigentuemerakte_liefert_die_person(self):
        person = Person.objects.create(
            personennummer='P-API-1', person_typ='100', vorname='Erika',
            nachname='Musterfrau')
        EigentumsVerhaeltnis.objects.create(
            person=person, einheit=self.einheit, beginn=date(2020, 1, 1))

        antwort = self.client.get('/api/v1/akten/eigentuemerakte/',
                                  {'person': str(person.id)})

        self.assertEqual(antwort.status_code, 200)
        self.assertIn('Musterfrau', antwort.data['titel'])


class AktenregisterApiTest(AktenApiBasis):
    def test_unterregister_anlegen(self):
        antwort = self.client.post('/api/v1/aktenregister/', {
            'code': '05/A', 'bezeichnung': 'Hebeanlage',
            'aktenart': 'haus', 'eltern': str(self.wartung.id),
            'objekt': str(self.objekt.id), 'sortierung': 51,
        }, format='json')

        self.assertEqual(antwort.status_code, 201)
        self.assertEqual(antwort.data['eltern_bezeichnung'], '05 Wartung')

    def test_ohne_objekt_wird_abgelehnt(self):
        # Die gemeinsame Gliederung ist Stammdatenpflege — entstünde sie
        # nebenbei beim Ablegen, driftete sie zwischen den Objekten
        # auseinander.
        antwort = self.client.post('/api/v1/aktenregister/', {
            'code': '22', 'bezeichnung': 'Neu', 'aktenart': 'haus',
            'eltern': str(self.wartung.id),
        }, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_ohne_elternregister_wird_abgelehnt(self):
        antwort = self.client.post('/api/v1/aktenregister/', {
            'code': '22', 'bezeichnung': 'Neu', 'aktenart': 'haus',
            'objekt': str(self.objekt.id),
        }, format='json')
        self.assertEqual(antwort.status_code, 400)

    def test_gemeinsames_register_ist_nicht_loeschbar(self):
        antwort = self.client.delete(f'/api/v1/aktenregister/{self.wartung.id}/')
        self.assertEqual(antwort.status_code, 400)
        self.assertTrue(Aktenregister.objects.filter(pk=self.wartung.pk).exists())

    def test_register_mit_dokumenten_ist_nicht_loeschbar(self):
        eigenes = Aktenregister.objects.create(
            code='05/B', bezeichnung='Lüftung', sortierung=52,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.objekt)
        self._dokument('lueftung.pdf', register=eigenes, objekt=self.objekt)

        antwort = self.client.delete(f'/api/v1/aktenregister/{eigenes.id}/')

        self.assertEqual(antwort.status_code, 400)
        self.assertIn('Dokumente', antwort.data['detail'])

    def test_leeres_eigenes_register_ist_loeschbar(self):
        eigenes = Aktenregister.objects.create(
            code='05/C', bezeichnung='Pumpe', sortierung=53,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.objekt)

        antwort = self.client.delete(f'/api/v1/aktenregister/{eigenes.id}/')

        self.assertEqual(antwort.status_code, 204)
        self.assertFalse(Aktenregister.objects.filter(pk=eigenes.pk).exists())


class DokumentEinsortierenApiTest(AktenApiBasis):
    def test_dokument_einsortieren(self):
        dokument = self._dokument('unsortiert.pdf', objekt=self.objekt)

        antwort = self.client.post(
            f'/api/v1/dokumente/{dokument.id}/einsortieren/',
            {'register': str(self.wartung.id)}, format='json')

        self.assertEqual(antwort.status_code, 200)
        dokument.refresh_from_db()
        self.assertEqual(dokument.register, self.wartung)

    def test_wieder_herausnehmen(self):
        dokument = self._dokument('x.pdf', register=self.wartung, objekt=self.objekt)

        antwort = self.client.post(
            f'/api/v1/dokumente/{dokument.id}/einsortieren/',
            {'register': None}, format='json')

        self.assertEqual(antwort.status_code, 200)
        dokument.refresh_from_db()
        self.assertIsNone(dokument.register_id)

    def test_fremdes_objektregister_wird_abgelehnt(self):
        # Sonst läge das Dokument in einem Register, das in seiner eigenen
        # Akte gar nicht erscheint — unauffindbar, ohne Fehlermeldung.
        fremdes_register = Aktenregister.objects.create(
            code='05/Z', bezeichnung='Fremd', sortierung=59,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=self.wartung, objekt=self.fremdes)
        dokument = self._dokument('meins.pdf', objekt=self.objekt)

        antwort = self.client.post(
            f'/api/v1/dokumente/{dokument.id}/einsortieren/',
            {'register': str(fremdes_register.id)}, format='json')

        self.assertEqual(antwort.status_code, 400)
        dokument.refresh_from_db()
        self.assertIsNone(dokument.register_id)


class RegistervorschlagApiTest(AktenApiBasis):
    """Der Vorschlag-Endpoint — er SCHLAEGT vor, setzt aber nichts.

    Getestet wird die deterministische Dokumenttyp-Stufe (beschluss -> "15"):
    sie braucht keinen API-Schluessel und keinen Claude-Aufruf.
    """

    def _beschluss(self, dateiname='beschluss.pdf'):
        dokument = self._dokument(dateiname, objekt=self.objekt)
        dokument.dokument_typ = 'beschluss'
        dokument.save(update_fields=['dokument_typ'])
        return dokument

    def test_dokumenttyp_regel_schlaegt_register_vor(self):
        dokument = self._beschluss()

        antwort = self.client.get(
            f'/api/v1/dokumente/{dokument.id}/registervorschlag/',
            {'objekt': str(self.objekt.id)})

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['quelle'], 'dokumenttyp')
        self.assertEqual(antwort.data['code'], '15')
        self.assertIsNotNone(antwort.data['register_id'])

    def test_vorschlag_setzt_das_register_nicht(self):
        # Vorschlagen, nicht einsortieren: bis jemand "Übernehmen" klickt,
        # bleibt das Dokument unsortiert.
        dokument = self._beschluss('beschluss2.pdf')

        self.client.get(
            f'/api/v1/dokumente/{dokument.id}/registervorschlag/',
            {'objekt': str(self.objekt.id)})

        dokument.refresh_from_db()
        self.assertIsNone(dokument.register_id)

    def test_ohne_anmeldung_kein_zugriff(self):
        dokument = self._beschluss('beschluss3.pdf')
        self.client.force_authenticate(None)

        antwort = self.client.get(
            f'/api/v1/dokumente/{dokument.id}/registervorschlag/',
            {'objekt': str(self.objekt.id)})

        self.assertEqual(antwort.status_code, 401)


class KreditorakteApiTest(AktenApiBasis):
    """Die Kreditorenakte: Belege eines Kreditors, nach Objekt gruppiert.

    Belege sind kontextlose Rechnungsbelege (Owner ist die Rechnung); sie
    werden deshalb per ``Dokument.objects.create`` angelegt, nicht ueber
    ``full_clean`` — genau wie in der realen Kopplung.
    """

    def setUp(self):
        super().setUp()
        self.kreditor = Kreditor.objects.create(name='Muster Handwerk GmbH')

    def _beleg(self, dateiname, kreditor, objekt):
        dok = Dokument.objects.create(
            datei=ContentFile(b'%PDF-1.4 x', name=dateiname),
            dateiname=dateiname, kategorie='Beleg', dokument_typ='beleg',
            hochgeladen_von=self.user)
        Rechnung.objects.create(objekt=objekt, kreditor=kreditor, beleg_dokument=dok)
        return dok

    def test_gruppiert_belege_nach_objekt(self):
        self._beleg('a1.pdf', self.kreditor, self.objekt)
        self._beleg('a2.pdf', self.kreditor, self.objekt)
        self._beleg('b1.pdf', self.kreditor, self.fremdes)

        antwort = self.client.get('/api/v1/akten/kreditorenakte/',
                                  {'kreditor': str(self.kreditor.id)})

        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.data['anzahl_dokumente'], 3)
        gruppen = antwort.data['objekte']
        # Nach Objektnummer sortiert: API01 vor API02.
        self.assertEqual([g['objektnummer'] for g in gruppen], ['API01', 'API02'])
        self.assertEqual([g['anzahl'] for g in gruppen], [2, 1])

    def test_fremder_kreditor_nicht_enthalten(self):
        anderer = Kreditor.objects.create(name='Andere Firma')
        self._beleg('meins.pdf', self.kreditor, self.objekt)
        self._beleg('fremd.pdf', anderer, self.objekt)

        antwort = self.client.get('/api/v1/akten/kreditorenakte/',
                                  {'kreditor': str(self.kreditor.id)})

        self.assertEqual(antwort.data['anzahl_dokumente'], 1)
        namen = [d['dateiname']
                 for g in antwort.data['objekte'] for d in g['dokumente']]
        self.assertEqual(namen, ['meins.pdf'])

    def test_beleg_ohne_objekt_landet_in_ohne_objekt(self):
        self._beleg('kein_objekt.pdf', self.kreditor, None)

        antwort = self.client.get('/api/v1/akten/kreditorenakte/',
                                  {'kreditor': str(self.kreditor.id)})

        letzte = antwort.data['objekte'][-1]
        self.assertEqual(letzte['bezeichnung'], 'Ohne Objekt')
        self.assertIsNone(letzte['objekt_id'])

    def test_ohne_kreditor_parameter_kommt_400(self):
        self.assertEqual(
            self.client.get('/api/v1/akten/kreditorenakte/').status_code, 400)

    def test_ohne_anmeldung_kein_zugriff(self):
        self.client.force_authenticate(None)
        antwort = self.client.get('/api/v1/akten/kreditorenakte/',
                                  {'kreditor': str(self.kreditor.id)})
        self.assertEqual(antwort.status_code, 401)


class AnzeigenameTest(AktenApiBasis):
    """Der Titel ersetzt den Dateinamen in der ANZEIGE — nicht die Datei.

    Der Dateiname bleibt die Bruecke zum Archivordner, gehoert bei
    revisionssicheren Belegen zur Nachvollziehbarkeit und ist der Name,
    unter dem der Absender sein Dokument kennt.
    """

    def test_ohne_titel_gilt_der_dateiname(self):
        dokument = self._dokument('Scan_20260914_001.pdf', objekt=self.objekt)
        self.assertEqual(dokument.anzeigename, 'Scan_20260914_001.pdf')

    def test_titel_hat_vorrang(self):
        dokument = self._dokument('Scan_20260914_001.pdf', objekt=self.objekt)
        dokument.titel = 'Wartungsvertrag Hebeanlage 2026'
        dokument.save(update_fields=['titel'])
        self.assertEqual(dokument.anzeigename, 'Wartungsvertrag Hebeanlage 2026')

    def test_dateiname_bleibt_unveraendert(self):
        dokument = self._dokument('original.pdf', objekt=self.objekt)
        dokument.titel = 'Etwas ganz anderes'
        dokument.save(update_fields=['titel'])
        dokument.refresh_from_db()
        self.assertEqual(dokument.dateiname, 'original.pdf')

    def test_api_liefert_beides(self):
        dokument = self._dokument('lang_und_kryptisch.pdf',
                                  register=self.wartung, objekt=self.objekt)
        dokument.titel = 'Kurz und klar'
        dokument.save(update_fields=['titel'])

        antwort = self.client.get('/api/v1/akten/hausakte/',
                                  {'objekt': str(self.objekt.id)})

        gruppe = next(r for r in antwort.data['register'] if r['code'] == '05')
        zeile = gruppe['dokumente'][0]
        self.assertEqual(zeile['anzeigename'], 'Kurz und klar')
        self.assertEqual(zeile['dateiname'], 'lang_und_kryptisch.pdf')
