"""
Datenmigration: technischer System-User 'immocore-portal' für
``Vorgang.erstellt_von`` bei Vorgängen aus dem Eigentümer-Portal.

Portal-Identitäten (``PortalNutzer``/``PortalSession``, siehe
``apps.portal.auth``) haben BEWUSST keinen ``auth.User`` — wer tatsächlich
Antragsteller ist, steht in ``Vorgang.person`` zusammen mit
``quelle='portal'``. ``Vorgang.erstellt_von`` ist aber ein Pflichtfeld
(PROTECT-FK auf ``auth.User``), daher dieser unbenutzbare Platzhalter-User
(analog 'immocore-autopilot', siehe
``apps.buchhaltung.migrations.0025_autopilot_user``). Login ist über
``set_unusable_password`` ausgeschlossen, der User bleibt zusätzlich
``is_active=False``.

Idempotent: prüft vor der Anlage auf Existenz (get_or_create-Charakter),
läuft also auch dann gefahrlos, wenn der User bereits (z.B. über
``vorgang_service.portal_system_user``) angelegt wurde.
"""
from django.db import migrations

PORTAL_SYSTEM_USERNAME = 'immocore-portal'


def create_portal_system_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    if not User.objects.filter(username=PORTAL_SYSTEM_USERNAME).exists():
        # password='!' entspricht UNUSABLE_PASSWORD_PREFIX — kein Login möglich
        User.objects.create(
            username=PORTAL_SYSTEM_USERNAME,
            first_name='IMMOCORE',
            last_name='Portal',
            email='portal@noreply.immocore.local',
            is_active=False,
            is_staff=False,
            is_superuser=False,
            password='!portal-no-login',
        )


def delete_portal_system_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username=PORTAL_SYSTEM_USERNAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vorgaenge', '0005_vorgangereignis_intern_alter_vorgangereignis_typ'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_portal_system_user, delete_portal_system_user),
    ]
