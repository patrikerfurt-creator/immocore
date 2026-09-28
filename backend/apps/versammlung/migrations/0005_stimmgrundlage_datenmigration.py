"""
Datenmigration: EVStimmgrundlage aus stimmprinzip/stimm_verteilerschluessel
(Spec v1.1 Kap. 2, "Migration Bestandsdaten").

Für jede bestehende ``Eigentuemerversammlung`` entsteht GENAU EINE
``EVStimmgrundlage`` — kopiert (nicht neu berechnet!) aus dem alten
``stimmprinzip``/``stimm_verteilerschluessel``-Wertepaar:

* ``stimmprinzip='kopf'`` → ``ist_kopfprinzip=True`` (das alte Kopfprinzip war
  bereits personenbezogen — ``stimmkraft_service._stimmkraft_kopf`` — und
  entspricht damit exakt dem neuen ``ist_kopfprinzip``, nicht dem
  Objektprinzip von ``Verteilerschluessel.vs_typ='kopf'``).
* ``stimmprinzip='verteilerschluessel'`` → ``verteilerschluessel`` +
  ``wirtschaftsjahr`` werden 1:1 übernommen.

Alle TOPs der EV werden auf diese eine Stimmgrundlage gesetzt.
``EVTeilnehmer.stimmkraft`` wird UNVERÄNDERT in ``EVTeilnehmerStimmkraft``
kopiert (keine Neuberechnung — das würde Stimmgewichte bereits
abgeschlossener Versammlungen nachträglich ändern), ebenso
``EVTeilnehmerAnteil.mea_wert_snapshot`` nach ``EVTeilnehmerAnteilWert``.
Je migrierter EV entsteht ein ``EVEreignis`` (typ='kommentar') als
Audit-Hinweis.

Reverse ist bewusst ``noop``: nach der Snapshot-Kopie in die neuen Modelle
gibt es keinen verlustfreien Weg zurück (mehrere Stimmgrundlagen könnten
inzwischen zusätzlich angelegt worden sein, TOPs zeigen bereits auf die neue
FK) — ein sauberes Reverse wäre nur eine Attrappe und würde Daten stumm
verwerfen. Ein Downgrade dieser Migration ist daher nicht vorgesehen; im
Zweifel: Restore aus dem Datenbank-Backup vor der Migration.
"""
from django.db import migrations


def migriere(apps, schema_editor):
    Eigentuemerversammlung = apps.get_model('versammlung', 'Eigentuemerversammlung')
    EVStimmgrundlage = apps.get_model('versammlung', 'EVStimmgrundlage')
    EVTeilnehmerStimmkraft = apps.get_model('versammlung', 'EVTeilnehmerStimmkraft')
    EVTeilnehmerAnteilWert = apps.get_model('versammlung', 'EVTeilnehmerAnteilWert')
    EVEreignis = apps.get_model('versammlung', 'EVEreignis')

    for ev in Eigentuemerversammlung.objects.all().iterator():
        # Idempotent: eine EV, die schon eine Stimmgrundlage hat (z.B. erneuter
        # Migrationslauf oder bereits über den neuen Weg angelegt), wird
        # übersprungen.
        if EVStimmgrundlage.objects.filter(ev=ev).exists():
            continue

        if ev.stimmprinzip == 'verteilerschluessel' and ev.stimm_verteilerschluessel_id:
            vs = ev.stimm_verteilerschluessel
            grundlage = EVStimmgrundlage.objects.create(
                ev=ev,
                verteilerschluessel=vs,
                ist_kopfprinzip=False,
                wirtschaftsjahr=ev.stimm_wirtschaftsjahr,
                ist_standard=True,
                bezeichnung_anzeige=f'{vs.schluessel} {vs.bezeichnung}'.strip(),
            )
            herkunft = f'stimmprinzip="verteilerschluessel" ({vs.schluessel} {vs.bezeichnung})'
        else:
            grundlage = EVStimmgrundlage.objects.create(
                ev=ev,
                verteilerschluessel=None,
                ist_kopfprinzip=True,
                wirtschaftsjahr=0,
                ist_standard=True,
                bezeichnung_anzeige='Kopfprinzip',
            )
            herkunft = f'stimmprinzip="{ev.stimmprinzip}"'

        ev.tagesordnung.all().update(stimmgrundlage=grundlage)

        for teilnehmer in ev.teilnehmer.all():
            EVTeilnehmerStimmkraft.objects.get_or_create(
                teilnehmer=teilnehmer, stimmgrundlage=grundlage,
                defaults={'stimmkraft': teilnehmer.stimmkraft},
            )
            for anteil in teilnehmer.anteile.all():
                EVTeilnehmerAnteilWert.objects.get_or_create(
                    anteil=anteil, stimmgrundlage=grundlage,
                    defaults={'wert_snapshot': anteil.mea_wert_snapshot},
                )

        EVEreignis.objects.create(
            ev=ev, top=None, typ='kommentar',
            text=(
                'Datenmodell-Migration v1.1: Stimmgrundlage übernommen aus '
                f'{herkunft}. Stimmkraft-Snapshots wurden kopiert, nicht neu '
                'berechnet.'
            ),
            alter_wert='', neuer_wert=grundlage.bezeichnung_anzeige,
            erstellt_von=None,
        )


def rueckwaerts_nicht_vorgesehen(apps, schema_editor):
    """Bewusst ``noop`` — siehe Modul-Docstring: ein verlustfreies Reverse ist
    nach der Snapshot-Kopie nicht sinnvoll möglich (siehe Begründung oben)."""


class Migration(migrations.Migration):

    dependencies = [
        ('versammlung', '0004_versammlungsort_stimmgrundlage'),
    ]

    operations = [
        migrations.RunPython(migriere, rueckwaerts_nicht_vorgesehen),
    ]
