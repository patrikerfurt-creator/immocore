from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mitarbeiter', '0001_initial'),
        ('objekte', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MitarbeiterObjektZuordnung',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('mitarbeiter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='objekt_zuordnungen',
                    to='mitarbeiter.mitarbeiter',
                )),
                ('objekt', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mitarbeiter_zuordnungen',
                    to='objekte.objekt',
                )),
            ],
            options={
                'verbose_name':        'Mitarbeiter-Objekt-Zuordnung',
                'verbose_name_plural': 'Mitarbeiter-Objekt-Zuordnungen',
                'ordering':            ['mitarbeiter__user__last_name'],
                'unique_together':     {('mitarbeiter', 'objekt')},
            },
        ),
    ]
