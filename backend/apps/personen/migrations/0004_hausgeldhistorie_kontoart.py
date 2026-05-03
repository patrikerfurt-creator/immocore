from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('personen', '0003_person_typ_nummern'),
    ]
    operations = [
        migrations.AddField(
            model_name='hausgeldhistorie',
            name='kontoart',
            field=models.CharField(max_length=10, blank=True, default='', help_text='z.B. .900, .911, .912, .940'),
        ),
    ]
