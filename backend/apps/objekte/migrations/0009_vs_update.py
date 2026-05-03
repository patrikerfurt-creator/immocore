from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0008_alter_bankkonto_iban'),
    ]

    operations = [
        # Verteilerschluessel: neue Felder hinzufügen
        migrations.AddField(
            model_name='verteilerschluessel',
            name='schluessel',
            field=models.CharField(blank=True, default='', max_length=3),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='verteilerschluessel',
            name='vs_typ',
            field=models.CharField(
                blank=True, null=True, max_length=20,
                choices=[('flaeche', 'Fläche'), ('mea', 'MEA'), ('kopf', 'Kopf'),
                         ('direkt', 'Direkt'), ('verbrauch', 'Verbrauch')],
            ),
        ),
        migrations.AddField(
            model_name='verteilerschluessel',
            name='aktiv',
            field=models.BooleanField(default=True),
        ),
        # Update ordering
        migrations.AlterModelOptions(
            name='verteilerschluessel',
            options={
                'ordering': ['objekt', 'schluessel', 'bezeichnung'],
                'verbose_name': 'Verteilerschlüssel',
                'verbose_name_plural': 'Verteilerschlüssel',
            },
        ),

        # VerteilerschluesselWert: neue Felder + unique_together ändern
        migrations.AlterField(
            model_name='verteilerschluesselwert',
            name='wert',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='verteilerschluesselwert',
            name='wirtschaftsjahr',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='verteilerschluesselwert',
            name='beteiligt',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='verteilerschluesselwert',
            name='einzelwert_einheit',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='verteilerschluesselwert',
            name='quelle',
            field=models.CharField(
                choices=[('stammdaten', 'Stammdaten'), ('manuell', 'Manuell')],
                default='stammdaten', max_length=20,
            ),
        ),
        # unique_together: alte Einschränkung entfernen, neue hinzufügen
        migrations.AlterUniqueTogether(
            name='verteilerschluesselwert',
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name='verteilerschluesselwert',
            unique_together={('schluessel', 'einheit', 'wirtschaftsjahr')},
        ),
        # Bankkonto: kontoinhaber optional machen
        migrations.AlterField(
            model_name='bankkonto',
            name='kontoinhaber',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
