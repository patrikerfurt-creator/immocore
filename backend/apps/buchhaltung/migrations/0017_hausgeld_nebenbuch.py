import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def init_opos_sequenzen(apps, schema_editor):
    Objekt = apps.get_model('objekte', 'Objekt')
    OposSequenz = apps.get_model('buchhaltung', 'OposSequenz')
    for o in Objekt.objects.all():
        OposSequenz.objects.get_or_create(objekt=o)


def set_tilgungs_prioritaet(apps, schema_editor):
    Buchungsart = apps.get_model('buchhaltung', 'Buchungsart')
    BA_PRIO = {
        '911': (20,   'ruecklage_nach_index', '41911'),
        '912': (21,   'ruecklage_nach_index', '41912'),
        '913': (22,   'ruecklage_nach_index', '41913'),
        '900': (90,   'bewirtschaftung',      '41900'),
        '950': (None, 'bewirtschaftung',      '41950'),
        '940': (None, 'frei',                 '41940'),
    }
    for nr, (prio, bk_typ, erloeskonto_nr) in BA_PRIO.items():
        Buchungsart.objects.filter(nr=nr).update(
            tilgungs_prioritaet=prio,
            bankkonto_typ=bk_typ,
            erloeskonto_default_nr=erloeskonto_nr,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0016_buchung_wirtschaftsjahr_fk'),
        ('objekte',     '0016_bankkonto_zahlungsverkehr'),
        ('konten',      '0005_data_migration_wj'),
        ('personen',    '0009_hausgeldhistorie_abrechnungsart'),
        ('auth',        '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Buchungsart Erweiterungen
        migrations.AddField(
            model_name='buchungsart',
            name='tilgungs_prioritaet',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='buchungsart',
            name='erloeskonto_default_nr',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='buchungsart',
            name='bankkonto_typ',
            field=models.CharField(
                blank=True, null=True, max_length=25,
                choices=[
                    ('bewirtschaftung',      'Bewirtschaftungskonto'),
                    ('ruecklage_nach_index', 'Ruecklage nach Konto-Index'),
                    ('frei',                 'Frei konfigurierbar'),
                ],
            ),
        ),

        # HausgeldSollstellungslauf
        migrations.CreateModel(
            name='HausgeldSollstellungslauf',
            fields=[
                ('id',                    models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('typ',                   models.CharField(max_length=30, choices=[
                    ('hausgeld_monat', 'Hausgeld monatlich'),
                    ('sonderumlage', 'Sonderumlage'),
                    ('abrechnungsergebnis_jahr', 'Abrechnungsergebnis'),
                ])),
                ('periode',               models.DateField()),
                ('status',                models.CharField(max_length=20, default='vorschau', choices=[
                    ('vorschau', 'Vorschau'),
                    ('commited', 'Bestaetigt'),
                    ('storniert', 'Storniert'),
                ])),
                ('anzahl_sollstellungen', models.IntegerField(default=0)),
                ('summe',                 models.DecimalField(max_digits=14, decimal_places=2, default=0)),
                ('erstellt_am',           models.DateTimeField(auto_now_add=True)),
                ('commited_am',           models.DateTimeField(blank=True, null=True)),
                ('storniert_am',          models.DateTimeField(blank=True, null=True)),
                ('storniert_grund',       models.TextField(blank=True)),
                ('objekt',                models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='hausgeld_laeufe', to='objekte.objekt')),
                ('erstellt_von',          models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('commited_von',          models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('storniert_von',         models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-periode', 'objekt']},
        ),

        # OposSequenz
        migrations.CreateModel(
            name='OposSequenz',
            fields=[
                ('objekt',          models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, related_name='opos_sequenz', serialize=False, to='objekte.objekt')),
                ('naechste_lfd_nr', models.BigIntegerField(default=1)),
            ],
        ),

        # HausgeldSollstellung
        migrations.CreateModel(
            name='HausgeldSollstellung',
            fields=[
                ('id',                models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('sollstellungs_typ', models.CharField(max_length=20, choices=[
                    ('hausgeld', 'Hausgeld'),
                    ('sonderumlage', 'Sonderumlage'),
                    ('abrechnungsergebnis', 'Abrechnungsergebnis'),
                ])),
                ('periode',           models.DateField()),
                ('faellig_am',        models.DateField()),
                ('opos_nr',           models.CharField(max_length=15, unique=True, db_index=True)),
                ('soll_betrag',       models.DecimalField(max_digits=12, decimal_places=2)),
                ('ist_betrag',        models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ('status_cached',     models.CharField(max_length=20, default='offen', db_index=True)),
                ('storniert_am',      models.DateTimeField(blank=True, null=True)),
                ('storniert_grund',   models.TextField(blank=True)),
                ('erstellt_am',       models.DateTimeField(auto_now_add=True)),
                ('objekt',            models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='hausgeld_sollstellungen', to='objekte.objekt')),
                ('eigentumsverhaeltnis', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sollstellungen', to='personen.eigentumsverhaeltnis')),
                ('ba',                models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='buchhaltung.buchungsart')),
                ('sollstellungslauf', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sollstellungen', to='buchhaltung.hausgeldsollstellungslauf')),
                ('storniert_von',     models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('erstellt_von',      models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-periode', 'eigentumsverhaeltnis']},
        ),
        migrations.AddConstraint(
            model_name='hausgeldsollstellung',
            constraint=models.UniqueConstraint(
                fields=['eigentumsverhaeltnis', 'periode', 'sollstellungs_typ', 'ba'],
                name='uniq_sollstellung_ev_periode_typ_ba',
            ),
        ),
        migrations.AddIndex(
            model_name='hausgeldsollstellung',
            index=models.Index(fields=['objekt', 'status_cached'], name='idx_hg_ss_objekt_status'),
        ),
        migrations.AddIndex(
            model_name='hausgeldsollstellung',
            index=models.Index(fields=['opos_nr'], name='idx_hg_ss_opos_nr'),
        ),

        # SollstellungSplit
        migrations.CreateModel(
            name='SollstellungSplit',
            fields=[
                ('id',               models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('betrag',           models.DecimalField(max_digits=12, decimal_places=2)),
                ('ist_betrag_split', models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ('sollstellung',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='splits', to='buchhaltung.hausgeldsollstellung')),
                ('ba',               models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='buchhaltung.buchungsart')),
                ('bankkonto_ziel',   models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='objekte.bankkonto')),
                ('erloeskonto',      models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='konten.konto')),
            ],
        ),
        migrations.AddConstraint(
            model_name='sollstellungsplit',
            constraint=models.UniqueConstraint(
                fields=['sollstellung', 'ba'],
                name='uniq_split_sollstellung_ba',
            ),
        ),

        # SollstellungZahlung
        migrations.CreateModel(
            name='SollstellungZahlung',
            fields=[
                ('id',            models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('betrag',        models.DecimalField(max_digits=12, decimal_places=2)),
                ('tilgungsstufe', models.CharField(max_length=20, default='hauptforderung', choices=[
                    ('hauptforderung', 'Hauptforderung'),
                    ('zinsen', 'Zinsen'),
                    ('kosten', 'Kosten'),
                ])),
                ('erstellt_am',   models.DateTimeField(auto_now_add=True)),
                ('sollstellung',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='zahlungen', to='buchhaltung.hausgeldsollstellung')),
                ('split',         models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='zahlungen', to='buchhaltung.sollstellungsplit')),
                ('buchung',       models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sollstellung_zahlungen', to='buchhaltung.buchung')),
                ('erstellt_von',  models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['erstellt_am']},
        ),

        # Datenmigration
        migrations.RunPython(init_opos_sequenzen, migrations.RunPython.noop),
        migrations.RunPython(set_tilgungs_prioritaet, migrations.RunPython.noop),
    ]
