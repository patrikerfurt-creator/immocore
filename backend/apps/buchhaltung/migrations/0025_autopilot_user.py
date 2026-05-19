"""
Datenmigration: System-User 'immocore-autopilot' anlegen.
Dieser User darf nicht für den Login benutzt werden (set_unusable_password).
"""
from django.db import migrations


def create_autopilot_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    if not User.objects.filter(username='immocore-autopilot').exists():
        # password='!' entspricht UNUSABLE_PASSWORD_PREFIX — kein Login möglich
        User.objects.create(
            username='immocore-autopilot',
            first_name='IMMOCORE',
            last_name='Autopilot',
            email='autopilot@noreply.immocore.local',
            is_active=True,
            is_staff=False,
            is_superuser=False,
            password='!autopilot-no-login',
        )


def delete_autopilot_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username='immocore-autopilot').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('buchhaltung', '0024_sollstellung_bankkonto_nullable_und_lauf_fehler'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_autopilot_user, delete_autopilot_user),
    ]
