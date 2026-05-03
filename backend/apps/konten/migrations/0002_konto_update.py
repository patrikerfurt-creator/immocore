from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('konten', '0001_initial'),
    ]

    operations = [
        # 1. Rename fields
        migrations.RenameField(model_name='konto', old_name='nummer', new_name='kontonummer'),
        migrations.RenameField(model_name='konto', old_name='bezeichnung', new_name='kontoname'),

        # 2. Remove old fields
        migrations.RemoveField(model_name='konto', name='klasse'),

        # 3. Alter verteilerschluessel: drop choices, shorten max_length, allow null
        migrations.AlterField(
            model_name='konto',
            name='verteilerschluessel',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),

        # 4. Alter kontoname max_length
        migrations.AlterField(
            model_name='konto',
            name='kontoname',
            field=models.CharField(max_length=120),
        ),

        # 5. Alter kontonummer max_length
        migrations.AlterField(
            model_name='konto',
            name='kontonummer',
            field=models.CharField(max_length=6),
        ),

        # 6. Add new fields
        migrations.AddField(
            model_name='konto',
            name='abrechnungsart',
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AddField(
            model_name='konto',
            name='direktes_buchen',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='konto',
            name='kontoart',
            field=models.CharField(
                choices=[('standard', 'Standard'), ('summierung', 'Summierungskonto'), ('unterkonto', 'Unterkonto')],
                default='standard',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='konto',
            name='arge_konto',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='konto',
            name='arge_kostenart',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),

        # 7. Update unique_together (rename applied automatically by Django for field renames)
        migrations.AlterUniqueTogether(
            name='konto',
            unique_together={('objekt', 'kontonummer')},
        ),

        # 8. Update ordering
        migrations.AlterModelOptions(
            name='konto',
            options={
                'ordering': ['kontonummer'],
                'verbose_name': 'Konto (Sachkonto)',
                'verbose_name_plural': 'Konten (Sachkonten)',
            },
        ),
    ]
