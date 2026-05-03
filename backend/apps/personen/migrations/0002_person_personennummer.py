from django.db import migrations, models


def vergib_nummern(apps, schema_editor):
    Person = apps.get_model('personen', 'Person')
    for i, person in enumerate(Person.objects.order_by('id'), start=100001):
        person.personennummer = str(i)
        person.save(update_fields=['personennummer'])


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0001_initial'),
    ]

    operations = [
        # Erst ohne unique anlegen
        migrations.AddField(
            model_name='person',
            name='personennummer',
            field=models.CharField(blank=True, max_length=20, default=''),
        ),
        # Bestehende Datensätze befüllen
        migrations.RunPython(vergib_nummern, migrations.RunPython.noop),
        # Jetzt unique setzen
        migrations.AlterField(
            model_name='person',
            name='personennummer',
            field=models.CharField(blank=True, max_length=20, unique=True),
        ),
    ]
