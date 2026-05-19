import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0017_hausgeld_nebenbuch'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='hausgeldsollstellungslauf',
            name='freigabe_user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='freigegebene_hausgeld_laeufe',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='hausgeldsollstellungslauf',
            name='freigegeben_am',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='hausgeldsollstellungslauf',
            name='status',
            field=models.CharField(
                choices=[
                    ('vorschau', 'Vorschau'),
                    ('freigegeben', 'Freigegeben (Vier-Augen)'),
                    ('commited', 'Commited / Ausgefuehrt'),
                    ('storniert', 'Storniert'),
                ],
                default='vorschau',
                max_length=20,
            ),
        ),
    ]
