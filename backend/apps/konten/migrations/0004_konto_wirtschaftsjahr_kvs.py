"""Schritt 1: KontoVerteilerSchluessel anlegen, wirtschaftsjahr-FK an Konto hinzufügen.
Schritt 2: Datenmigration — für jedes Objekt ein erstes Wirtschaftsjahr anlegen,
           Konten daran binden, KontoVerteilerSchluessel aus konto.verteilerschluessel
           materialisieren.
Schritt 3: objekt-FK von Konto entfernen.
"""
import uuid
from datetime import date

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def _konto_wj_erstellen(apps, schema_editor):
    """Datenmigration: Wirtschaftsjahr je Objekt, Konten binden, KVS materialisieren."""
    Objekt          = apps.get_model('objekte', 'Objekt')
    Wirtschaftsjahr = apps.get_model('objekte', 'Wirtschaftsjahr')
    Konto           = apps.get_model('konten',  'Konto')
    KontoVS         = apps.get_model('konten',  'KontoVerteilerSchluessel')

    aktuelles_jahr = timezone.now().year

    for objekt in Objekt.objects.all():
        startjahr = (
            objekt.verwaltung_seit.year
            if objekt.verwaltung_seit
            else aktuelles_jahr
        )
        wj, _ = Wirtschaftsjahr.objects.get_or_create(
            objekt=objekt,
            jahr=startjahr,
            defaults={
                'beginn_monat': objekt.wirtschaftsjahr_start or 1,
                'status': 'offen',
            },
        )
        wj_beginn = date(wj.jahr, wj.beginn_monat, 1)

        # Alle Konten dieses Objekts an das WJ binden
        for konto in Konto.objects.filter(objekt_id=objekt.pk, wirtschaftsjahr__isnull=True):
            konto.wirtschaftsjahr = wj
            konto.save(update_fields=['wirtschaftsjahr'])

            # VS-Zuordnung materialisieren
            if konto.verteilerschluessel:
                KontoVS.objects.get_or_create(
                    konto=konto,
                    vs_code=konto.verteilerschluessel,
                    defaults={'gueltig_ab': wj_beginn},
                )


def _konto_wj_rueckgaengig(apps, schema_editor):
    Wirtschaftsjahr = apps.get_model('objekte', 'Wirtschaftsjahr')
    Konto           = apps.get_model('konten',  'Konto')
    Konto.objects.all().update(wirtschaftsjahr=None)
    Wirtschaftsjahr.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('konten',  '0003_abrechnungsart'),
        ('objekte', '0015_wirtschaftsjahr_einheitverbrauch'),
    ]

    operations = [
        # 1. KontoVerteilerSchluessel-Tabelle erstellen
        migrations.CreateModel(
            name='KontoVerteilerSchluessel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('vs_code', models.CharField(max_length=3)),
                ('gueltig_ab', models.DateField()),
            ],
            options={
                'verbose_name': 'Konto-Verteilerschlüssel',
                'verbose_name_plural': 'Konto-Verteilerschlüssel',
                'ordering': ['konto', 'gueltig_ab'],
            },
        ),
        # 2. Alten unique_together entfernen
        migrations.AlterUniqueTogether(
            name='konto',
            unique_together=set(),
        ),
        # 3. wirtschaftsjahr-FK hinzufügen (nullable)
        migrations.AddField(
            model_name='konto',
            name='wirtschaftsjahr',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='konten',
                to='objekte.wirtschaftsjahr',
            ),
        ),
        # 4. Neuer unique constraint
        migrations.AddConstraint(
            model_name='konto',
            constraint=models.UniqueConstraint(
                condition=models.Q(wirtschaftsjahr__isnull=False),
                fields=('wirtschaftsjahr', 'kontonummer'),
                name='unique_wj_kontonummer',
            ),
        ),
        # 5. FK von KontoVerteilerSchluessel → Konto
        migrations.AddField(
            model_name='kontoverteilerschluessel',
            name='konto',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='vs_zuordnungen',
                to='konten.konto',
            ),
        ),
        # 6. Datenmigration (läuft solange objekt-Spalte noch existiert)
        migrations.RunPython(_konto_wj_erstellen, _konto_wj_rueckgaengig),
        # 7. objekt-FK entfernen
        migrations.RemoveField(
            model_name='konto',
            name='objekt',
        ),
    ]
