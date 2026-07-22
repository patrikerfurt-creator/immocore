"""HGA-Spec v1.0 Phase A — Umbau Jahresabrechnung/EinzelAbrechnung (Kap. 3 + 10).

Beide Tabellen sind bei Anlage dieser Migration leer (Feature noch nicht
produktiv), daher reine Schema-Migration ohne Daten-Migration. Die neuen
Pflicht-FKs (wirtschaftsjahr, prozess, eigentuemer, eigentumsverhaeltnis)
werden als NOT NULL ohne Default hinzugefügt — auf leerer Tabelle gefahrlos.

Ablösung Ausgangsspec Kap. 4.9:
- gebucht (Boolean) entfällt, ersetzt durch sollstellung-FK (Kap. 3.2/10)
- eigentuemer_snapshot (JSON) + personenkonto entfallen, ersetzt durch
  eigentuemer- und eigentumsverhaeltnis-FK (Snapshot via FK)
- pdf_pfad (String) entfällt, ersetzt durch dokument-FK
- wirtschaftsjahr (IntegerField) wird FK auf objekte.Wirtschaftsjahr
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0043_buchungsart_richtung'),
        ('objekte', '0021_alter_objekt_auto_pipeline_aktiv_and_more'),
        ('prozesse', '0001_initial'),
        ('personen', '0019_person_emails_telefonnummern'),
        ('dokumente', '0002_add_beleg_belegnummerzaehler'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -------------------------------------------------------------------
        # Jahresabrechnung
        # -------------------------------------------------------------------
        migrations.AlterUniqueTogether(
            name='jahresabrechnung',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='jahresabrechnung',
            name='erstellungsdatum',
            field=models.DateField(
                auto_now_add=True,
                help_text='Bestimmt den „aktuellen Eigentümer" je Einheit (Kap. 6.1).',
            ),
        ),
        migrations.RemoveField(
            model_name='jahresabrechnung',
            name='wirtschaftsjahr',
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='wirtschaftsjahr',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='jahresabrechnungen',
                to='objekte.wirtschaftsjahr',
                help_text="Muss status='offen' haben bei Anlage (Service-Validierung).",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='prozess',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='jahresabrechnungen',
                to='prozesse.prozess',
                help_text='Wizard-Zwischenstand (Prozess-Engine).',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='freigegeben_am',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='freigegeben_von',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='freigegebene_jahresabrechnungen',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='sollstellungslauf',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='jahresabrechnungen',
                to='buchhaltung.hausgeldsollstellungslauf',
                help_text='Gesetzt nach erfolgreichem run_abrechnungsergebnis (Schritt 8).',
            ),
        ),
        migrations.AddField(
            model_name='jahresabrechnung',
            name='erstellt_am',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='jahresabrechnung',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'storniert'), _negated=True),
                fields=('objekt', 'wirtschaftsjahr'),
                name='jahresabrechnung_unique_je_wj',
            ),
        ),
        # -------------------------------------------------------------------
        # EinzelAbrechnung
        # -------------------------------------------------------------------
        migrations.RemoveField(
            model_name='einzelabrechnung',
            name='gebucht',
        ),
        migrations.RemoveField(
            model_name='einzelabrechnung',
            name='eigentuemer_snapshot',
        ),
        migrations.RemoveField(
            model_name='einzelabrechnung',
            name='personenkonto',
        ),
        migrations.RemoveField(
            model_name='einzelabrechnung',
            name='pdf_pfad',
        ),
        migrations.AddField(
            model_name='einzelabrechnung',
            name='eigentuemer',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='einzelabrechnungen',
                to='personen.person',
                help_text='Snapshot zum erstellungsdatum — bleibt korrekt nach späterem Wechsel.',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='einzelabrechnung',
            name='eigentumsverhaeltnis',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='einzelabrechnungen',
                to='personen.eigentumsverhaeltnis',
                help_text='Snapshot-Referenz für Nebenbuch-Verknüpfung.',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='einzelabrechnung',
            name='sollstellung',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='einzelabrechnungen',
                to='buchhaltung.hausgeldsollstellung',
                help_text='Gesetzt nach Schritt 8 — Verknüpfung zur Nebenbuch-Sollstellung.',
            ),
        ),
        migrations.AddField(
            model_name='einzelabrechnung',
            name='dokument',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='einzelabrechnungen',
                to='dokumente.dokument',
                help_text='Gesetzt nach PDF-Erzeugung in Schritt 7/8.',
            ),
        ),
        migrations.AddField(
            model_name='einzelabrechnung',
            name='hinweis_eigentuemerwechsel',
            field=models.BooleanField(
                default=False,
                help_text='Steuert Fußnote im PDF (Kap. 6.3).',
            ),
        ),
        migrations.AlterField(
            model_name='einzelabrechnung',
            name='hausgeld_soll_gesamt',
            field=models.DecimalField(decimal_places=2, max_digits=14),
        ),
        migrations.AlterField(
            model_name='einzelabrechnung',
            name='kostenanteil_gesamt',
            field=models.DecimalField(decimal_places=2, max_digits=14),
        ),
        migrations.AlterField(
            model_name='einzelabrechnung',
            name='abrechnungsergebnis',
            field=models.DecimalField(
                decimal_places=2, max_digits=14,
                help_text='kostenanteil_gesamt - hausgeld_soll_gesamt; >0 Nachzahlung, <0 Guthaben.',
            ),
        ),
        migrations.AddConstraint(
            model_name='einzelabrechnung',
            constraint=models.UniqueConstraint(
                fields=('jahresabrechnung', 'einheit'),
                name='einzelabrechnung_unique_je_einheit',
            ),
        ),
    ]
