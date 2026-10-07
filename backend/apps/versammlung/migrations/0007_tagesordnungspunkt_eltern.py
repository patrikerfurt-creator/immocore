# Generated for IMMOCORE: TOP-Hierarchie (Unterpunkte 3.1, 3.2).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('versammlung', '0006_beschluss_ergebnis'),
    ]

    operations = [
        migrations.AddField(
            model_name='tagesordnungspunkt',
            name='eltern',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='unterpunkte',
                to='versammlung.tagesordnungspunkt',
                verbose_name='Übergeordneter TOP',
                help_text='Gesetzt, wenn dieser Punkt ein Unterpunkt ist (z.B. '
                          'TOP 3.1 unter TOP 3). Nur eine Ebene: ein '
                          'Unterpunkt kann nicht weiter unterteilt werden. Ein '
                          'TOP mit Unterpunkten ist ein Gliederungspunkt — '
                          'über ihn wird NICHT abgestimmt, die Abstimmung '
                          'erfolgt auf seinen Unterpunkten.',
            ),
        ),
        migrations.AlterField(
            model_name='tagesordnungspunkt',
            name='nummer',
            field=models.IntegerField(
                help_text='Fortlaufend ab 1 je Ebene — Haupt-TOPs und die '
                          'Unterpunkte eines TOP werden getrennt gezählt. Die '
                          'Anzeige ("3.1") liefert die Property nummer_anzeige.',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='tagesordnungspunkt',
            name='uniq_top_nummer_je_ev',
        ),
        migrations.AddConstraint(
            model_name='tagesordnungspunkt',
            constraint=models.UniqueConstraint(
                fields=('ev', 'eltern', 'nummer'),
                name='uniq_top_nummer_je_ev_ebene',
                nulls_distinct=False,
            ),
        ),
    ]
