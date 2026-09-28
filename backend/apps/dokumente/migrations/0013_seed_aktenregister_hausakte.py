"""
Die Gliederung der Hausakte — Positionen 01 bis 21.

01-17 sind das Trennblätterverzeichnis der Demme GmbH, Bezeichnungen
unverändert übernommen: die Mitarbeiter kennen sie, und die Papierakten sind
physisch so sortiert. Eine "aufgeräumtere" Reihenfolge hätte mehr
Umgewöhnung gekostet als sie gebracht hätte.

18-21 sind Ergänzungen für die digitale Ablage, hinten angehängt statt
eingeschoben, damit sich an den bekannten Nummern nichts verschiebt:

  18  Instandhaltung — Pos. 05 "Wartung" deckt nur Wartungsverträge ab,
      nicht Schadensfälle, Angebote und Sanierungen.
  19  Abrechnung — fehlte im Papierverzeichnis ganz.
  20  Bank/Konten — dito.
  21  Schriftwechsel — der wichtigste Zuwachs: die importierten Mails
      hatten bisher kein Register und landeten unter "Ohne Register".

SORTIERUNG in Zehnerschritten (10, 20, 30 …), nicht 1, 2, 3: So lässt sich
später ein Register dazwischenschieben, ohne alle folgenden neu zu
nummerieren.

CODES zweistellig mit führender Null ("05" statt "5") — passend zur
Untergliederung im Original ("03 / A - Mustermann") und damit eine
alphabetische Sortierung dieselbe Reihenfolge ergibt wie eine numerische.
"""
import uuid

from django.db import migrations


HAUS = 'haus'
ALLE = 'alle'

# (code, bezeichnung, sortierung, aktenart, hinweis)
SEED = [
    ('01', 'Grundbesitzabgaben/Versorger', 10, HAUS,
     'Grundsteuer, Abfall, Straßenreinigung, Strom, Gas, Wasser.'),
    ('02', 'Hausmeister / -Service / Winterdienst / Außenanlagepflege', 20, HAUS,
     ''),
    ('03', 'Schornsteinfeger', 30, HAUS, ''),
    ('04', 'Messdienst', 40, HAUS,
     'Heizkostenverteiler, Wasserzähler, Ablesungen, Gerätewechsel.'),
    ('05', 'Wartung', 50, HAUS,
     'Wartungsverträge. Je Anlage bei Bedarf ein objektspezifisches '
     'Unterregister anlegen (z.B. "05/A Hebeanlage") — es erscheint dann nur '
     'in der Akte dieses Objekts. Schadensfälle und Reparaturen gehören '
     'nach 18.'),
    ('06', 'Versicherung', 60, HAUS,
     'Policen, Nachträge, Beitragsrechnungen. Ein Schadensfall ist ein '
     'Vorgang vom Typ "Versicherungsschaden", keine reine Ablage.'),
    ('07', 'Grundlagen / Fotos / Zeichnungen', 70, HAUS, ''),
    ('08', 'Schließplan', 80, HAUS, ''),
    ('09', 'Hausordnung', 90, HAUS, ''),
    ('10', 'Energieausweis', 100, HAUS, ''),
    ('11', 'Teilungserklärung', 110, HAUS,
     'Teilungserklärung, Gemeinschaftsordnung, Nachträge.'),
    ('12', 'Verwaltervertrag / Verwaltervollmacht', 120, HAUS, ''),
    ('13', 'Bauakte / Unterlagen Bauträger', 130, HAUS, ''),
    ('14', 'Beschlussprotokolle', 140, HAUS,
     'Das Protokoll selbst. Einladung, Tagesordnung und Vorbereitung '
     'gehören nach 16.'),
    ('15', 'Beschlusssammlung', 150, HAUS,
     'Nach § 24 Abs. 7 WEG eigenständig zu führen — nicht mit den '
     'Protokollen (14) vermischen.'),
    ('16', 'Eigentümerversammlungen', 160, HAUS,
     'Einladung, Tagesordnung, Vollmachten, Anwesenheitsliste. Das Protokoll '
     'gehört nach 14.'),
    ('17', 'Rechtsangelegenheiten', 170, HAUS,
     'Ein laufendes Verfahren wird als VORGANG geführt (Typ '
     '"Beschlussanfechtung" oder "Hausgeldklage") — nur dort gibt es Status, '
     'Fristen und Wiedervorlage. Hier liegen die Dokumente dazu.'),
    ('18', 'Instandhaltung / Schäden / Sanierung', 180, HAUS,
     'Reparaturen, Angebote, Gewährleistung. Größere Maßnahmen als '
     'Vorgang vom Typ "Sanierung / Bauprojekt" führen.'),
    ('19', 'Abrechnung / Wirtschaftsplan', 190, HAUS,
     'Jahresabrechnung, Einzelabrechnungen, Wirtschaftsplan, '
     'Einzelwirtschaftspläne — nach Wirtschaftsjahr gruppiert.'),
    ('20', 'Bank / Konten / Rücklagen', 200, HAUS,
     'Kontoeröffnung, Vollmachten, Rücklagenkonten, Kontoauszüge.'),
    # Als einziges Register aktenart='alle': Schriftwechsel fällt in jeder
    # Akte an — zum Objekt, zur Wohnung und zur Person. Dreimal anlegen
    # hieße, dass ein Mitarbeiter beim Ablegen zwischen drei gleich
    # benannten Registern wählen müsste.
    ('21', 'Schriftwechsel allgemein', 210, ALLE,
     'Korrespondenz, die zu keinem Sachregister gehört. Fällt ein Brief '
     'klar unter ein Thema, gehört er dorthin — hier bleibt der Rest.'),
]


def seed(apps, schema_editor):
    Aktenregister = apps.get_model('dokumente', 'Aktenregister')
    for code, bezeichnung, sortierung, aktenart, hinweis in SEED:
        Aktenregister.objects.get_or_create(
            code=code, objekt=None,
            defaults={
                'id': uuid.uuid4(),
                'bezeichnung': bezeichnung,
                'sortierung': sortierung,
                'aktenart': aktenart,
                'hinweis': hinweis,
                'aktiv': True,
            },
        )


def unseed(apps, schema_editor):
    """Entfernt nur leere Register.

    ``Dokument.register`` ist PROTECT — ein Register mit abgelegten
    Dokumenten lässt sich ohnehin nicht löschen. Statt die Migration daran
    scheitern zu lassen, bleiben benutzte Register stehen. Ebenso solche,
    unter denen jemand eine objektspezifische Untergliederung angelegt hat:
    die hinge sonst in der Luft.
    """
    Aktenregister = apps.get_model('dokumente', 'Aktenregister')
    for code, *_ in SEED:
        register = Aktenregister.objects.filter(code=code, objekt__isnull=True).first()
        if (register and not register.dokumente.exists()
                and not register.unterregister.exists()):
            register.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dokumente', '0012_aktenregister_objekt_alter_aktenregister_code_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
