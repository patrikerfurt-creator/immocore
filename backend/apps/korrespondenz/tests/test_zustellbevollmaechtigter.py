"""Integrationstest: Schreiben an einen Eigentümer mit Zustellungsbevollmächtigtem.

Ist ein Bevollmächtigter hinterlegt, trägt das Schreiben dessen Anschrift, Name
und Anrede (Darstellung „Nur Bevollmächtigter"), und die Kanalwahl richtet sich
nach dessen Zustellweg. Der ``Schreiben.empfaenger`` bleibt der Eigentümer.
"""
from django.utils import timezone

from apps.korrespondenz.services import schreiben_service
from apps.personen.models import Person

from .basis_versand import VersandTestBasis


class SchreibenMitBevollmaechtigtemTest(VersandTestBasis):
    def _bevollmaechtigter(self, **felder):
        basis = dict(
            personennummer='ZB-1', person_typ='500', anrede='Frau', vorname='Berta',
            nachname='Bevoll', strasse='Vertreterstraße', hausnummer='9', plz='12345',
            ort='Berlin',
        )
        basis.update(felder)
        return Person.objects.create(**basis)

    def test_anschrift_und_name_sind_die_des_bevollmaechtigten(self):
        zb = self._bevollmaechtigter()
        self.s.person.zustellungsbevollmaechtigter = zb
        self.s.person.save(update_fields=['zustellungsbevollmaechtigter'])

        # Vorlage, die Name und Anschrift des Empfängers explizit referenziert,
        # damit beides im Snapshot landet (nur benutzte Platzhalter werden gesichert).
        version = self.vorlage(inhalt=[{
            'typ': 'text',
            'inhalt': 'Empfänger {{ empfaenger.name }} {{ empfaenger.anschrift_zeilen }}',
        }])
        schreiben = schreiben_service.erstelle_aus_version(
            version, self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            eigentumsverhaeltnis=self.s.ev, user=self.user,
        )

        # Der Datensatz bleibt beim Eigentümer …
        self.assertEqual(schreiben.empfaenger_id, self.s.person.id)
        # … aber das Schreiben adressiert den Bevollmächtigten.
        snap = schreiben.kontext_snapshot
        self.assertEqual(snap['empfaenger.name'], zb.name)
        zeilen = ' '.join(snap['empfaenger.anschrift_zeilen'])
        self.assertIn('Vertreterstraße 9', zeilen)
        self.assertIn('Berlin', zeilen)
        self.assertNotIn('Musterweg', zeilen)  # Eigentümer-Adresse taucht nicht auf

    def test_kanalwahl_folgt_dem_bevollmaechtigten(self):
        """Eigentümer ohne Mail-Zustimmung, Bevollmächtigter mit → Kanal E-Mail."""
        zb = self._bevollmaechtigter(
            emails=[{'adresse': 'berta@example.org'}],
            zustellweg='email', zustellweg_zustimmung_am=timezone.now(),
        )
        self.s.person.zustellungsbevollmaechtigter = zb
        self.s.person.save(update_fields=['zustellungsbevollmaechtigter'])

        version = self.vorlage(kanal_standard='beides')
        schreiben = schreiben_service.erstelle_aus_version(
            version, self.s.person, objekt=self.s.objekt, einheit=self.s.einheit,
            eigentumsverhaeltnis=self.s.ev, user=self.user,
        )
        self.assertEqual(schreiben.kanal, 'email')
