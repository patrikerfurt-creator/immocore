"""
Stimmkraft-Grundlage: Verteilerschlüssel statt festem Enum
(Patrik-Entscheidung 2026-08-20, Spec v1.1 offener Punkt 8).

``stimmprinzip`` kannte 'kopf' / 'objekt' / 'mea'. Neu: 'kopf' bleibt (§ 25
Abs. 2 WEG), 'objekt' und 'mea' werden durch 'verteilerschluessel' + FK
ersetzt. Damit sind auch Regelungen wie "nur Wohnungen stimmen mit" (VS 031)
abbildbar, ohne den Code zu ändern.

Die Datenmigration bildet Bestandszeilen ab: 'objekt' → VS 030 ("Anzahl
Einheiten Gesamt", auf allen Objekten gepflegt), 'mea' → VS 010 ("MEA
Gesamt"). Findet sich der passende Schlüssel am Objekt nicht, fällt die Zeile
bewusst auf 'kopf' zurück — der gesetzliche Regelfall ist die sichere Wahl,
eine halb konfigurierte Stimmgrundlage wäre gefährlicher.
"""
from django.db import migrations, models
import django.db.models.deletion

# Schlüssel der Muster-Verteilerschlüssel (konten.services.MUSTER_VS)
_SCHLUESSEL_JE_ALTPRINZIP = {
    'objekt': '030',
    'mea':    '010',
}


def migriere_stimmprinzip(apps, schema_editor):
    EV = apps.get_model('versammlung', 'Eigentuemerversammlung')
    Verteilerschluessel = apps.get_model('objekte', 'Verteilerschluessel')

    for ev in EV.objects.exclude(stimmprinzip='kopf').iterator():
        schluessel = _SCHLUESSEL_JE_ALTPRINZIP.get(ev.stimmprinzip)
        vs = None
        if schluessel:
            vs = (
                Verteilerschluessel.objects
                .filter(objekt_id=ev.objekt_id, schluessel=schluessel, aktiv=True)
                .order_by('schluessel').first()
            )
        if vs is None:
            ev.stimmprinzip = 'kopf'
            ev.stimm_verteilerschluessel = None
        else:
            ev.stimmprinzip = 'verteilerschluessel'
            ev.stimm_verteilerschluessel = vs
        ev.save(update_fields=['stimmprinzip', 'stimm_verteilerschluessel'])


def migriere_zurueck(apps, schema_editor):
    EV = apps.get_model('versammlung', 'Eigentuemerversammlung')
    for ev in EV.objects.filter(stimmprinzip='verteilerschluessel').iterator():
        schluessel = getattr(ev.stimm_verteilerschluessel, 'schluessel', '')
        ev.stimmprinzip = 'mea' if schluessel == '010' else 'objekt'
        ev.stimm_verteilerschluessel = None
        ev.save(update_fields=['stimmprinzip', 'stimm_verteilerschluessel'])


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0001_initial'),
        ('versammlung', '0002_seed_vorgangtyp_ev_beschluss'),
    ]

    operations = [
        migrations.RenameField(
            model_name='eigentuemerversammlung',
            old_name='mea_wirtschaftsjahr',
            new_name='stimm_wirtschaftsjahr',
        ),
        migrations.AlterField(
            model_name='eigentuemerversammlung',
            name='stimm_wirtschaftsjahr',
            field=models.IntegerField(
                default=0,
                help_text='Wirtschaftsjahr, aus dem die Werte gelesen werden; '
                          '0 = zeitlos (Regelfall bei flaeche/mea/kopf, siehe '
                          'VerteilerschluesselWert.wirtschaftsjahr).',
                verbose_name='Wirtschaftsjahr des Stimm-Verteilerschlüssels',
            ),
        ),
        migrations.AddField(
            model_name='eigentuemerversammlung',
            name='stimm_verteilerschluessel',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='eigentuemerversammlungen',
                to='objekte.verteilerschluessel',
                help_text='Grundlage der Stimmkraft bei stimmprinzip='
                          '"verteilerschluessel" — z.B. "030 Anzahl Einheiten '
                          'Gesamt" (eine Stimme je Einheit), "031 Anzahl '
                          'Wohnungen" (Stellplätze stimmen nicht mit) oder '
                          '"010 MEA Gesamt" (Wertprinzip). Damit ist jede '
                          'Regelung der Teilungserklärung abbildbar, ohne den '
                          'Code zu ändern.',
                verbose_name='Stimm-Verteilerschlüssel',
            ),
        ),
        migrations.AlterField(
            model_name='eigentuemerversammlung',
            name='stimmprinzip',
            field=models.CharField(
                choices=[
                    ('kopf', 'Kopfprinzip (§ 25 Abs. 2 WEG: eine Stimme je Eigentümer)'),
                    ('verteilerschluessel', 'Nach Verteilerschlüssel'),
                ],
                default='kopf', max_length=20,
                help_text='Gesetzlicher Regelfall ist das Kopfprinzip (eine '
                          'Stimme je Eigentümer, unabhängig von der Anzahl der '
                          'Einheiten); abweichende Regelungen stehen in der '
                          'Teilungserklärung und werden über einen '
                          'Verteilerschlüssel abgebildet.',
            ),
        ),
        migrations.RunPython(migriere_stimmprinzip, migriere_zurueck),
    ]
