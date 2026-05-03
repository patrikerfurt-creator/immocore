from django.db import migrations, models

MAPPING = {
    'Eigentuemer': '100',
    'Mieter': '200',
    'Dienstleister': '300',
    'Sonstiges': '400',
}


def konvertiere_typen(apps, schema_editor):
    Person = apps.get_model('personen', 'Person')
    for person in Person.objects.all():
        person.person_typ = MAPPING.get(person.person_typ, '400')
        person.save(update_fields=['person_typ'])


class Migration(migrations.Migration):

    dependencies = [
        ('personen', '0002_person_personennummer'),
    ]

    operations = [
        migrations.RunPython(konvertiere_typen, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='person',
            name='person_typ',
            field=models.CharField(
                choices=[
                    ('100', 'Eigentümer'),
                    ('200', 'Mieter'),
                    ('300', 'Kreditor'),
                    ('400', 'Sonstiges'),
                ],
                max_length=100
            ),
        ),
    ]
