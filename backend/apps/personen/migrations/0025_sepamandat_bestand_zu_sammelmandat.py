"""Bestandsmandate dem Mandatsgeber zuordnen (Sammelmandat).

Fuer jedes ``SEPAMandat`` ohne ``person`` wird gezaehlt, wie viele Personen
es ueber ``Person.sepa_mandat`` referenzieren:

* genau 1 -> ``mandat.person`` wird gesetzt, ``eigentumsverhaeltnis`` bleibt
  NULL (= Sammelmandat fuer alle Einheiten der Person)
* 0 oder >= 2 -> unveraendert, nur Logausgabe (Legacy-Rueckfall im Resolver
  haelt das bisherige Verhalten). Kein Klonen, kein Abbruch.

Idempotent: ein zweiter Lauf findet keine Mandate mit ``person IS NULL`` mehr,
die genau einen Referenten haben. Rueckwaerts: No-Op (gesetzte Zuordnungen
sind fachlich korrekt und von manuell gepflegten nicht unterscheidbar; die
Felder selbst entfernt 0024 rueckwaerts).
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _bestand_zu_sammelmandat(apps, schema_editor):
    SEPAMandat = apps.get_model('personen', 'SEPAMandat')
    Person = apps.get_model('personen', 'Person')

    for mandat in SEPAMandat.objects.filter(person__isnull=True).order_by('mandatsreferenz'):
        referenten = list(
            Person.objects.filter(sepa_mandat_id=mandat.id).values_list('id', flat=True)[:2]
        )
        if len(referenten) == 1:
            mandat.person_id = referenten[0]
            mandat.save(update_fields=['person'])
        else:
            anzahl = Person.objects.filter(sepa_mandat_id=mandat.id).count()
            logger.warning(
                'SEPAMandat %s: %d referenzierende Personen - Zuordnung nicht eindeutig, unveraendert.',
                mandat.mandatsreferenz, anzahl,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0024_sepamandat_person_ev_quelle'),
    ]

    operations = [
        migrations.RunPython(_bestand_zu_sammelmandat, migrations.RunPython.noop),
    ]
