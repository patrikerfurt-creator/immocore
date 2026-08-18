"""
API-Tests für die INTERNEN Handwerker-Endpunkte (Phase C, Orchestrator-
Vorgabe Schritt 6): Anlage aus Vorgang/eigenständig, Dashboard-Filter,
Statuswechsel, Kommentar, erneuter Versand, Rechnungszuordnung, Gewerke.

Mailversand wird durch ``captureOnCommitCallbacks`` in Django-``TestCase``
(hier via ``APITestCase``) ohnehin NIE ausgeführt, weil die gesamte Anfrage
in einer Transaktion läuft, die am Testende zurückgerollt wird — kein
``locmem`` nötig, es wird schlicht kein Task ausgelöst.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.handwerker.models import (
    AuftragsbestaetigungsToken,
    Gewerk,
    Handwerkerauftrag,
    ObjektHandwerker,
)
from apps.objekte.models import Objekt
from apps.rechnungen.models import Kreditor, Rechnung
from apps.vorgaenge.models import Vorgang, VorgangTyp

User = get_user_model()

HANDWERKERAUFTRAEGE = '/api/v1/handwerkerauftraege/'
GEWERKE = '/api/v1/gewerke/'
GEWERKE_ADMIN = '/api/v1/gewerke/admin/'
VORGAENGE = '/api/v1/vorgaenge/'


def _objekt(nr='HWK001'):
    return Objekt.objects.create(
        bezeichnung='Test-WEG Handwerker-API', objektnummer=nr, objekt_typ='weg',
        strasse='Teststraße 1', plz='12345', ort='Teststadt',
        verwaltung_seit=date(2020, 1, 1), bundesland='HE',
    )


def _kreditor(name='Meister Sanitär GmbH', ist_handwerker=True, email='meister@example.de', gewerke=None):
    kreditor = Kreditor.objects.create(name=name, ist_handwerker=ist_handwerker, email=email)
    if gewerke:
        kreditor.gewerke.set(gewerke)
    return kreditor


def _vorgang(user, objekt=None, einheit=None, person=None):
    typ = VorgangTyp.objects.get(code='maengelmeldung')
    return Vorgang.objects.create(
        typ=typ, betreff='Testvorgang', erstellt_von=user,
        objekt=objekt, einheit=einheit, person=person,
    )


def _rechnung(objekt, kreditor, **kwargs):
    defaults = dict(
        objekt=objekt, kreditor=kreditor, status='importiert',
        betrag_brutto=Decimal('100.00'), rechnungsnummer='RE-1',
    )
    defaults.update(kwargs)
    return Rechnung.objects.create(**defaults)


class HandwerkerauftragAusVorgangAnlageTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='hwk-vorgang-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def test_anlage_mit_objektbezug_erfolgreich(self):
        vorgang = _vorgang(self.user, objekt=self.objekt)
        response = self.client.post(f'{VORGAENGE}{vorgang.id}/handwerkerauftrag/', {
            'kreditor': str(self.kreditor.id),
            'titel': 'Heizung defekt',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'entwurf')
        self.assertEqual(response.data['objekt'], self.objekt.id)
        self.assertEqual(response.data['vorgang']['id'], vorgang.id)
        self.assertEqual(response.data['vorgang']['nummer'], vorgang.nummer)

    def test_anlage_ohne_objektbezug_ohne_objekt_gibt_400(self):
        from apps.personen.models import Person
        person = Person.objects.create(person_typ='100', vorname='Max', nachname='Mustermann')
        vorgang = _vorgang(self.user, person=person)
        response = self.client.post(f'{VORGAENGE}{vorgang.id}/handwerkerauftrag/', {
            'kreditor': str(self.kreditor.id),
            'titel': 'Ohne Objektbezug',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Objekt', response.data['detail'])

    def test_anlage_ohne_objektbezug_mit_explizitem_objekt_gibt_201(self):
        from apps.personen.models import Person
        person = Person.objects.create(person_typ='100', vorname='Max', nachname='Mustermann')
        vorgang = _vorgang(self.user, person=person)
        response = self.client.post(f'{VORGAENGE}{vorgang.id}/handwerkerauftrag/', {
            'kreditor': str(self.kreditor.id),
            'titel': 'Mit explizitem Objekt',
            'objekt': str(self.objekt.id),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['objekt'], self.objekt.id)


class HandwerkerauftragStandaloneAnlageTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='hwk-standalone-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def test_anlage_ohne_vorgang_mit_objekt_erfolgreich(self):
        response = self.client.post(HANDWERKERAUFTRAEGE, {
            'kreditor': str(self.kreditor.id),
            'titel': 'Rohrbruch',
            'objekt': str(self.objekt.id),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        auftrag = Handwerkerauftrag.objects.get(pk=response.data['id'])
        self.assertEqual(auftrag.erstellt_von, self.user)
        self.assertIsNone(auftrag.vorgang)

    def test_anlage_ohne_vorgang_und_ohne_objekt_gibt_400(self):
        response = self.client.post(HANDWERKERAUFTRAEGE, {
            'kreditor': str(self.kreditor.id),
            'titel': 'Ohne alles',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class HandwerkerauftragDashboardFilterTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='hwk-dashboard-tester')
        self.client.force_authenticate(self.user)
        self.objekt1 = _objekt('HWK010')
        self.objekt2 = _objekt('HWK011')
        self.kreditor1 = _kreditor('Sanitär Meier')
        self.kreditor2 = _kreditor('Elektro Schulz', email='schulz@example.de')

        self.a1 = Handwerkerauftrag.objects.create(
            objekt=self.objekt1, kreditor=self.kreditor1, titel='Wasserhahn tropft',
            erstellt_von=self.user, status='entwurf', prioritaet='hoch',
        )
        self.a2 = Handwerkerauftrag.objects.create(
            objekt=self.objekt2, kreditor=self.kreditor2, titel='Steckdose defekt',
            erstellt_von=self.user, status='versendet', prioritaet='normal',
        )
        self.a3 = Handwerkerauftrag.objects.create(
            objekt=self.objekt1, kreditor=self.kreditor1, titel='Dach undicht',
            erstellt_von=self.user, status='angenommen', prioritaet='normal',
        )

    def _ids(self, response):
        return {r['id'] for r in response.data['results']}

    def test_pagination_liefert_count_und_results(self):
        response = self.client.get(HANDWERKERAUFTRAEGE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 3)

    def test_filter_status_einzeln(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'status': 'versendet'})
        self.assertEqual(self._ids(response), {str(self.a2.id)})

    def test_filter_status_mehrere_kommagetrennt(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'status': 'entwurf,angenommen'})
        self.assertEqual(self._ids(response), {str(self.a1.id), str(self.a3.id)})

    def test_filter_objekt(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'objekt': str(self.objekt2.id)})
        self.assertEqual(self._ids(response), {str(self.a2.id)})

    def test_filter_kreditor(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'kreditor': str(self.kreditor2.id)})
        self.assertEqual(self._ids(response), {str(self.a2.id)})

    def test_filter_prioritaet(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'prioritaet': 'hoch'})
        self.assertEqual(self._ids(response), {str(self.a1.id)})

    def test_search_findet_ueber_titel(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'search': 'Steckdose'})
        self.assertEqual(self._ids(response), {str(self.a2.id)})

    def test_search_findet_ueber_nummer(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'search': self.a3.nummer})
        self.assertEqual(self._ids(response), {str(self.a3.id)})

    def test_ordering_nummer(self):
        response = self.client.get(HANDWERKERAUFTRAEGE, {'ordering': 'nummer'})
        nummern = [r['nummer'] for r in response.data['results']]
        self.assertEqual(nummern, sorted(nummern))


class HandwerkerauftragStatusAktionTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='hwk-status-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Testauftrag',
            erstellt_von=self.user, status='entwurf',
        )

    def test_gueltiger_uebergang_200(self):
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/status/', {
            'status': 'versendet',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'versendet')

    def test_ungueltiger_uebergang_400(self):
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/status/', {
            'status': 'abgeschlossen',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.status, 'entwurf')

    def test_abschluss_notiz_wird_bei_abgeschlossen_gespeichert(self):
        self.auftrag.status = 'angenommen'
        self.auftrag.save(update_fields=['status'])
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/status/', {
            'status': 'abgeschlossen',
            'abschluss_notiz': 'Alles erledigt, Rechnung folgt.',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.auftrag.refresh_from_db()
        self.assertEqual(self.auftrag.abschluss_notiz, 'Alles erledigt, Rechnung folgt.')


class HandwerkerauftragKommentarVersendenRechnungTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='hwk-aktionen-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Testauftrag',
            erstellt_von=self.user, status='versendet',
        )
        AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def test_kommentar_wird_angelegt(self):
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/kommentar/', {
            'text': 'Termin mit Mieter abgestimmt.',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.auftrag.ereignisse.filter(typ='kommentar').count(), 1)

    def test_erneut_versenden(self):
        alter_token = self.auftrag.token.accept_token
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/erneut-versenden/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.auftrag.refresh_from_db()
        self.assertNotEqual(self.auftrag.token.accept_token, alter_token)

    def test_erneut_versenden_aus_entwurf_nach_versandfehler(self):
        """Phase-D-Abnahme, Fehler 2: ein Auftrag mit fehlgeschlagenem ERSTEN
        Versand bleibt in 'entwurf' — der Endpunkt muss dort trotzdem
        funktionieren, sonst hängt der Auftrag unversendbar fest."""
        auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Versandfehler-Auftrag',
            erstellt_von=self.user, status='entwurf',
        )
        AuftragsbestaetigungsToken.objects.create(auftrag=auftrag)
        alter_token = auftrag.token.accept_token

        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{auftrag.id}/erneut-versenden/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        auftrag.refresh_from_db()
        self.assertEqual(auftrag.status, 'entwurf')
        self.assertNotEqual(auftrag.token.accept_token, alter_token)

    def test_rechnung_zuordnen(self):
        rechnung = _rechnung(self.objekt, self.kreditor)
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/rechnung-zuordnen/', {
            'rechnung': str(rechnung.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rechnung.refresh_from_db()
        self.assertEqual(rechnung.handwerkerauftrag_id, self.auftrag.id)

    def test_rechnung_zuordnen_fremder_kreditor_400(self):
        anderer_kreditor = _kreditor('Anderer Handwerker', email='anderer@example.de')
        rechnung = _rechnung(self.objekt, anderer_kreditor)
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/rechnung-zuordnen/', {
            'rechnung': str(rechnung.id),
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechnung_zuordnen_bereits_zugeordnet_400(self):
        anderer_auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Anderer Auftrag',
            erstellt_von=self.user,
        )
        rechnung = _rechnung(self.objekt, self.kreditor, handwerkerauftrag=anderer_auftrag)
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/rechnung-zuordnen/', {
            'rechnung': str(rechnung.id),
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechnung_loesen(self):
        rechnung = _rechnung(self.objekt, self.kreditor, handwerkerauftrag=self.auftrag)
        response = self.client.post(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/rechnung-loesen/', {
            'rechnung': str(rechnung.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rechnung.refresh_from_db()
        self.assertIsNone(rechnung.handwerkerauftrag_id)


class GewerkeTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='gewerke-tester')
        self.client.force_authenticate(self.user)
        self.aktiv = Gewerk.objects.create(code='testgewerk-aktiv', bezeichnung='Test-Gewerk aktiv', aktiv=True)
        self.inaktiv = Gewerk.objects.create(code='testgewerk-inaktiv', bezeichnung='Test-Gewerk inaktiv', aktiv=False)

    def test_liste_zeigt_nur_aktive(self):
        response = self.client.get(GEWERKE)
        codes = {g['code'] for g in response.data}
        self.assertIn('testgewerk-aktiv', codes)
        self.assertNotIn('testgewerk-inaktiv', codes)

    def test_admin_endpunkt_fuer_nicht_staff_403(self):
        response = self.client.get(GEWERKE_ADMIN)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_endpunkt_fuer_staff_erlaubt(self):
        staff = User.objects.create_user(username='gewerke-admin', is_staff=True)
        self.client.force_authenticate(staff)
        response = self.client.get(GEWERKE_ADMIN)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ObjektHandwerkerTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='objekt-hwk-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()

    def test_anlage_und_filter_nach_objekt(self):
        response = self.client.post('/api/v1/objekt-handwerker/', {
            'objekt': str(self.objekt.id),
            'kreditor': str(self.kreditor.id),
            'prioritaet': 1,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        liste = self.client.get('/api/v1/objekt-handwerker/', {'objekt': str(self.objekt.id)})
        self.assertEqual(len(liste.data), 1)
        self.assertEqual(liste.data[0]['kreditor_name'], self.kreditor.name)


class TokenLeakTest(APITestCase):
    """🔒 Pflicht-Test: accept_token/reject_token dürfen in KEINER Antwort der
    internen Endpunkte vorkommen (Orchestrator-Vorgabe Schritt 6)."""

    def setUp(self):
        self.user = User.objects.create_user(username='token-leak-tester')
        self.client.force_authenticate(self.user)
        self.objekt = _objekt()
        self.kreditor = _kreditor()
        self.auftrag = Handwerkerauftrag.objects.create(
            objekt=self.objekt, kreditor=self.kreditor, titel='Testauftrag',
            erstellt_von=self.user, status='entwurf',
        )
        self.token = AuftragsbestaetigungsToken.objects.create(auftrag=self.auftrag)

    def test_token_werte_nicht_in_liste(self):
        response = self.client.get(HANDWERKERAUFTRAEGE)
        inhalt = str(response.content)
        self.assertNotIn(self.token.accept_token, inhalt)
        self.assertNotIn(self.token.reject_token, inhalt)

    def test_token_werte_nicht_im_detail(self):
        response = self.client.get(f'{HANDWERKERAUFTRAEGE}{self.auftrag.id}/')
        inhalt = str(response.content)
        self.assertNotIn(self.token.accept_token, inhalt)
        self.assertNotIn(self.token.reject_token, inhalt)
        # Token-Status ist trotzdem enthalten (gueltig_bis/verbraucht_am).
        self.assertIn('token_status', inhalt)
