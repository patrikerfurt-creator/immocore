from django.db import migrations


def remove_vs101(apps, schema_editor):
    Verteilerschluessel = apps.get_model('objekte', 'Verteilerschluessel')
    Verteilerschluessel.objects.filter(schluessel='101').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('objekte', '0010_alter_einheit_options_alter_eingang_bezeichnung_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_vs101, migrations.RunPython.noop),
    ]
