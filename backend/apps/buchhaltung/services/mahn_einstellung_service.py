"""Objektspezifische Mahn-Konfiguration lesen/setzen (``MahnEinstellung``).

Die Existenz des Datensatzes schaltet das Mahnen für das Objekt frei
(``mahnwesen.konfig_fuer``). Änderungen wirken nur auf künftige Mahnläufe; bereits
erzeugte Mahnungen und Buchungen (eingefrorene Beträge) bleiben unberührt.
"""


def hole(objekt):
    """Die ``MahnEinstellung`` des Objekts oder ``None`` (Bestandsobjekt noch unkonfiguriert)."""
    from apps.buchhaltung.models import MahnEinstellung

    return MahnEinstellung.objects.filter(objekt=objekt).first()


def setze(objekt, mahngebuehr, anzahl_mahnstufen=2, zinsen_erheben=False):
    """Legt die Konfiguration an oder ersetzt sie vollständig; Rückgabe ``(einstellung, angelegt)``."""
    from apps.buchhaltung.models import MahnEinstellung

    einstellung, angelegt = MahnEinstellung.objects.update_or_create(
        objekt=objekt,
        defaults={
            'mahngebuehr': mahngebuehr,
            'anzahl_mahnstufen': anzahl_mahnstufen,
            'zinsen_erheben': zinsen_erheben,
        },
    )
    return einstellung, angelegt
