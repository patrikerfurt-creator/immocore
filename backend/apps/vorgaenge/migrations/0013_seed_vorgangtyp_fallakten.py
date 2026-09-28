"""
Vier Vorgangstypen fuer Fallakten: Faelle mit Laufzeit, Fristen und
Beteiligten — im Unterschied zu einem Aktenregister, das nur eine
thematische Schublade ist.

ZWEI EINSTELLUNGEN, DIE HIER BEWUSST SO GESETZT SIND:

``antwort_vorschlag_aktiv=False`` bei ALLEN vieren. Der KI-Antwortvorschlag
erzeugt sonst bei der Anlage automatisch einen versandfertigen Entwurf. Bei
einer Anfechtung oder Hausgeldklage waere das eine Rechtsauskunft, und genau
die verbietet der Prompt in ``antwort_vorschlag_service`` ausdruecklich — der
Entwurf soll hier gar nicht erst entstehen, statt sich auf die Selbst-
beschraenkung des Modells zu verlassen.

``portal_erstellbar=False`` ebenfalls bei allen. Am deutlichsten bei der
Hausgeldklage: Sie richtet sich GEGEN einen Eigentuemer — dass der sie im
Portal selbst anlegen kann, waere widersinnig.

PRIORITAETEN folgen den Fristen, nicht dem Aergernis:

- Anfechtung: § 45 WEG setzt AUSSCHLUSSfristen — Klage binnen eines Monats,
  Begruendung binnen zweier Monate ab Beschlussfassung. Versaeumt heisst
  verloren, unabhaengig davon, wie berechtigt die Sache war.
- Versicherungsschaden: Die Versicherer verlangen unverzuegliche Anzeige;
  eine spaete Meldung kostet im Zweifel den Deckungsschutz.
- Hausgeldklage: Verjaehrung und die Fristen des Mahnverfahrens.
- Sanierung: laeuft ueber Monate, aber ohne vergleichbaren Fristendruck.
"""
import uuid

from django.db import migrations


SEED = [
    # (code, bezeichnung, sortierung, standard_prioritaet)
    ('anfechtung',          'Beschlussanfechtung',   70,  'hoch'),
    ('hausgeldklage',       'Hausgeldklage',         80,  'hoch'),
    ('versicherungsschaden', 'Versicherungsschaden', 90,  'hoch'),
    ('sanierung',           'Sanierung / Bauprojekt', 100, 'normal'),
]


def seed(apps, schema_editor):
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    for code, bezeichnung, sortierung, prioritaet in SEED:
        VorgangTyp.objects.get_or_create(
            code=code,
            defaults={
                'id': uuid.uuid4(),
                'bezeichnung': bezeichnung,
                'sortierung': sortierung,
                'standard_prioritaet': prioritaet,
                'aktiv': True,
                'antwort_vorschlag_aktiv': False,
                'portal_erstellbar': False,
            },
        )


def unseed(apps, schema_editor):
    """Entfernt die Typen nur, solange kein Vorgang daran haengt.

    ``Vorgang.typ`` ist PROTECT — ein Loeschen mit bestehenden Vorgaengen
    wuerde ohnehin scheitern. Statt die Migration daran zerbrechen zu lassen,
    bleiben benutzte Typen einfach stehen.
    """
    VorgangTyp = apps.get_model('vorgaenge', 'VorgangTyp')
    for code, *_ in SEED:
        typ = VorgangTyp.objects.filter(code=code).first()
        if typ and not typ.vorgaenge.exists():
            typ.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vorgaenge', '0012_posteingang_status_ableiten'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
