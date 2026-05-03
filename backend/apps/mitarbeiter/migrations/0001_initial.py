from django.conf import settings
import django.contrib.postgres.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Mitarbeiter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('abteilungen', django.contrib.postgres.fields.ArrayField(
                    base_field=models.CharField(max_length=50),
                    default=list,
                    size=None,
                    verbose_name='Abteilungen',
                )),
                ('telefon',        models.CharField(blank=True, max_length=30)),
                ('aktiv',          models.BooleanField(default=True)),
                ('eingetreten_am', models.DateField(blank=True, null=True)),
                ('erstellt_am',    models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mitarbeiter_profil',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name':        'Mitarbeiter',
                'verbose_name_plural': 'Mitarbeiter',
                'ordering':            ['user__last_name', 'user__first_name'],
            },
        ),
    ]
