from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0012_lastschriftlauf'),
    ]

    operations = [
        migrations.AddField(
            model_name='lastschriftlauf',
            name='buchungen_erstellt',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='lastschriftlauf',
            name='buchungen_datum',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='lastschriftlauf',
            name='positionen',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='lastschriftlauf',
            name='ohne_mandat',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
