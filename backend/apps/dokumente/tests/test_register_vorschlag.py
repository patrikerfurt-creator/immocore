"""
Tests für den Registervorschlag.

Der wichtigste Teil sind die Fälle, in denen NICHTS gesetzt wird: zu geringe
Konfidenz, halluzinierter Code, ausgefallene KI. Ein falsch abgelegtes
Dokument findet niemand wieder — ein unsortiertes steht unter "Ohne
Register" und fällt auf. Die Zurückhaltung ist deshalb die eigentliche
Funktion, nicht ein Randfall.
"""
import shutil
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.dokumente.models import Aktenregister, Dokument
from apps.dokumente.services import akten_service, register_vorschlag_service
from apps.objekte.models import Objekt

User = get_user_model()

_MEDIA_TMP = tempfile.mkdtemp(prefix="immocore_test_media_regvorschlag_")


def tearDownModule():
    shutil.rmtree(_MEDIA_TMP, ignore_errors=True)


def ki_antwort(code=None, konfidenz=0.95, begruendung='Test'):
    """Baut eine Antwort, wie sie die Claude-API liefern würde."""
    class Block:
        type = 'text'

        def __init__(self, text):
            self.text = text

    class Antwort:
        def __init__(self, text):
            self.content = [Block(text)]

    import json
    return Antwort(json.dumps({
        'code': code, 'konfidenz': konfidenz, 'begruendung': begruendung}))


@override_settings(MEDIA_ROOT=_MEDIA_TMP, ANTHROPIC_API_KEY='test-key')
class RegisterVorschlagTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='reg-tester', password='x')
        self.objekt = Objekt.objects.create(
            bezeichnung='WEG Vorschlag', objektnummer='RV001', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))
        self.register = list(akten_service.register_einer_akte(
            Aktenregister.AKTENART_HAUS, objekt=self.objekt))

    def _dokument(self, dateiname='unsortiert.pdf', **felder):
        dokument = Dokument(
            datei=ContentFile(b'%PDF-1.4 x', name=dateiname),
            dateiname=dateiname, kategorie='Test',
            objekt=self.objekt, hochgeladen_von=self.user,
            **{'dokument_typ': 'sonstiges', **felder})
        dokument.full_clean()
        dokument.save()
        return dokument

    # -- Stufe 1: Dokumenttyp ---------------------------------------------

    def test_beschluss_geht_ohne_ki_in_die_beschlusssammlung(self):
        dokument = self._dokument('beschluss.pdf', dokument_typ='beschluss')

        with patch('anthropic.Anthropic') as mock_api:
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertEqual(vorschlag['register'].code, '15')
        self.assertEqual(vorschlag['quelle'], 'dokumenttyp')
        self.assertEqual(vorschlag['konfidenz'], 1.0)
        # Entscheidend: kein API-Aufruf.
        mock_api.assert_not_called()

    def test_abrechnung_geht_ohne_ki_in_register_19(self):
        dokument = self._dokument('ja2025.pdf', dokument_typ='abrechnung')
        with patch('anthropic.Anthropic') as mock_api:
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)
        self.assertEqual(vorschlag['register'].code, '19')
        mock_api.assert_not_called()

    # -- Stufe 2: KI -------------------------------------------------------

    def test_ki_vorschlag_wird_uebernommen(self):
        dokument = self._dokument('wasserschaden.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code='18', konfidenz=0.95, begruendung='Schadensfall')
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertEqual(vorschlag['register'].code, '18')
        self.assertEqual(vorschlag['quelle'], 'ki')
        self.assertEqual(vorschlag['konfidenz'], 0.95)

    def test_zu_geringe_konfidenz_setzt_nichts(self):
        dokument = self._dokument('unklar.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code='18', konfidenz=0.6)
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertIsNone(vorschlag['register'])
        self.assertEqual(vorschlag['konfidenz'], 0.6)
        self.assertIn('nicht gesetzt', vorschlag['begruendung'])

    def test_schwelle_wird_genau_eingehalten(self):
        dokument = self._dokument('grenzfall.pdf')
        schwelle = register_vorschlag_service.MINDESTKONFIDENZ

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code='18', konfidenz=schwelle)
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        # Genau auf der Schwelle wird noch gesetzt.
        self.assertIsNotNone(vorschlag['register'])

    def test_halluzinierter_code_wird_verworfen(self):
        dokument = self._dokument('x.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code='99', konfidenz=0.99)
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertIsNone(vorschlag['register'])
        self.assertIn('Unbekannter Registercode', vorschlag['fehler'])

    def test_ki_darf_sich_enthalten(self):
        # null statt eines Codes ist ein gueltiges Ergebnis — genau dafuer
        # steht es im Prompt.
        dokument = self._dokument('rätselhaft.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code=None, konfidenz=0.4, begruendung='')
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertIsNone(vorschlag['register'])
        self.assertEqual(vorschlag['fehler'], '')
        self.assertIn('eindeutig', vorschlag['begruendung'])

    def test_ki_ausfall_wirft_nicht(self):
        dokument = self._dokument('y.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.side_effect = RuntimeError(
                'API nicht erreichbar')
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, self.register)

        self.assertIsNone(vorschlag['register'])
        self.assertIn('API nicht erreichbar', vorschlag['fehler'])

    def test_ohne_register_kein_vorschlag(self):
        dokument = self._dokument('z.pdf')
        vorschlag = register_vorschlag_service.schlage_register_vor(dokument, [])
        self.assertIsNone(vorschlag['register'])
        self.assertIn('Keine Register', vorschlag['fehler'])

    def test_objektspezifisches_register_ist_waehlbar(self):
        wartung = Aktenregister.objects.get(code='05', objekt__isnull=True)
        Aktenregister.objects.create(
            code='05/A', bezeichnung='Hebeanlage', sortierung=51,
            aktenart=Aktenregister.AKTENART_HAUS,
            eltern=wartung, objekt=self.objekt)
        register = list(akten_service.register_einer_akte(
            Aktenregister.AKTENART_HAUS, objekt=self.objekt))
        dokument = self._dokument('hebeanlage_wartung.pdf')

        with patch('anthropic.Anthropic') as mock_api:
            mock_api.return_value.messages.create.return_value = ki_antwort(
                code='05/A', konfidenz=0.93)
            vorschlag = register_vorschlag_service.schlage_register_vor(
                dokument, register)

        self.assertEqual(vorschlag['register'].code, '05/A')


@override_settings(MEDIA_ROOT=_MEDIA_TMP)
class RegisterZuordnenKommandoTest(TestCase):
    """Das Kommando aendert ohne --ja nichts — die Zusicherung, auf die sich
    ein Trockenlauf verlaesst."""

    def setUp(self):
        self.user = User.objects.create_user(username='reg-cmd', password='x')
        self.objekt = Objekt.objects.create(
            bezeichnung='WEG Kommando', objektnummer='RV002', objekt_typ='weg',
            ort='Teststadt', verwaltung_seit=date(2015, 1, 1))
        self.dokument = Dokument(
            datei=ContentFile(b'%PDF-1.4 x', name='beschluss.pdf'),
            dateiname='beschluss.pdf', kategorie='Test',
            dokument_typ='beschluss', objekt=self.objekt,
            hochgeladen_von=self.user)
        self.dokument.full_clean()
        self.dokument.save()

    def test_trockenlauf_aendert_nichts(self):
        from io import StringIO
        from django.core.management import call_command

        call_command('register_zuordnen', stdout=StringIO())

        self.dokument.refresh_from_db()
        self.assertIsNone(self.dokument.register_id)

    def test_mit_ja_wird_gesetzt(self):
        from io import StringIO
        from django.core.management import call_command

        call_command('register_zuordnen', '--ja', stdout=StringIO())

        self.dokument.refresh_from_db()
        self.assertEqual(self.dokument.register.code, '15')

    def test_bestehende_zuordnung_wird_nicht_ueberschrieben(self):
        # Wer von Hand einsortiert hat, hat recht.
        from io import StringIO
        from django.core.management import call_command

        versicherung = Aktenregister.objects.get(code='06', objekt__isnull=True)
        self.dokument.register = versicherung
        self.dokument.save(update_fields=['register'])

        call_command('register_zuordnen', '--ja', stdout=StringIO())

        self.dokument.refresh_from_db()
        self.assertEqual(self.dokument.register, versicherung)
