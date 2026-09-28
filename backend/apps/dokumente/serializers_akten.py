"""
Serializer für die Aktenansicht.

Die Akte wird als FLACHE Liste von Registergruppen ausgeliefert, jede mit
``ebene`` — nicht als verschachtelter Baum. Grund: Die Reihenfolge ist im
Service bereits richtig gelegt (jedes Unterregister direkt hinter seinem
Elternregister), und eine flache Liste mit Einrückungsstufe lässt sich in
der Oberfläche ohne Rekursion darstellen.
"""
from rest_framework import serializers

from apps.dokumente.models import Aktenregister, Dokument


class AktenDokumentSerializer(serializers.ModelSerializer):
    """Ein Dokument in der Akte — bewusst schmal gehalten.

    Die Akte zeigt Listen mit vielen Zeilen; alles, was nicht auf den ersten
    Blick gebraucht wird, holt die Detailansicht nach.
    """
    ist_mail = serializers.SerializerMethodField()
    herkunft = serializers.SerializerMethodField()
    # Der Name, der in der Liste steht: Titel, sonst aus der Rechnung
    # abgeleitet, sonst der Dateiname (siehe Dokument.anzeigename).
    anzeigename = serializers.CharField(read_only=True)

    class Meta:
        model = Dokument
        fields = [
            'id', 'dateiname', 'titel', 'anzeigename',
            'dokument_typ', 'kategorie', 'beschreibung',
            'dokument_datum', 'hochgeladen_am', 'version',
            'ist_mail', 'herkunft',
        ]
        read_only_fields = fields

    def get_ist_mail(self, obj) -> bool:
        return (obj.dateiname or '').lower().endswith(('.eml', '.msg'))

    def get_herkunft(self, obj) -> str:
        """Woher das Dokument kommt — der Kontext, über den es in DIESER
        Akte gelandet ist. Ohne das wirkt eine Hausakte wie ein Sammelsurium:
        man sieht nicht, ob ein Beleg am Objekt, an einer Wohnung oder an
        einem Vorgang hängt."""
        if obj.einheit_id:
            return f'Einheit {obj.einheit.einheit_nr}'
        if obj.vorgang_id:
            return f'Vorgang {obj.vorgang.nummer}'
        if obj.person_id:
            return f'Person {obj.person.name}'
        try:
            if obj.rechnung:
                return 'Rechnungsbeleg'
        except Exception:
            pass
        if obj.mail_import_id:
            return 'Mail-Import'
        return 'Objekt'


class RegisterGruppeSerializer(serializers.Serializer):
    """Ein Register mit seinen Dokumenten — auch wenn es leer ist.

    Leere Register bleiben bewusst in der Ausgabe: Eine Akte ohne die Zeile
    "Versicherungen" sähe aus wie eine Akte ohne Versicherungsbedarf.
    """
    register_id = serializers.SerializerMethodField()
    code = serializers.CharField()
    bezeichnung = serializers.CharField()
    pfad = serializers.CharField()
    ebene = serializers.IntegerField()
    objektspezifisch = serializers.BooleanField()
    anzahl = serializers.IntegerField()
    hinweis = serializers.SerializerMethodField()
    dokumente = AktenDokumentSerializer(many=True)

    def get_register_id(self, obj):
        register = obj.get('register')
        return str(register.id) if register else None

    def get_hinweis(self, obj) -> str:
        register = obj.get('register')
        return register.hinweis if register else ''


class AktenregisterSerializer(serializers.ModelSerializer):
    """Für das Anlegen objektspezifischer Untergliederung aus der Akte heraus."""
    eltern_bezeichnung = serializers.SerializerMethodField()

    class Meta:
        model = Aktenregister
        fields = [
            'id', 'code', 'bezeichnung', 'aktenart', 'eltern',
            'eltern_bezeichnung', 'objekt', 'sortierung', 'aktiv', 'hinweis',
        ]
        read_only_fields = ['id', 'eltern_bezeichnung']

    def get_eltern_bezeichnung(self, obj) -> str:
        return str(obj.eltern) if obj.eltern_id else ''

    def validate(self, daten):
        # Die Oberfläche legt ausschliesslich OBJEKTSPEZIFISCHE Register an.
        # Die gemeinsame Gliederung (01-21) ist Stammdatenpflege und gehört
        # in den Admin — sonst entstünde sie nebenbei beim Ablegen und
        # driftete zwischen den Objekten auseinander.
        if not daten.get('objekt'):
            raise serializers.ValidationError(
                'Aus der Akte heraus lassen sich nur objektspezifische '
                'Unterregister anlegen. Die gemeinsame Gliederung wird in '
                'der Verwaltung gepflegt.'
            )
        if not daten.get('eltern'):
            raise serializers.ValidationError(
                'Ein Unterregister braucht ein übergeordnetes Register.'
            )
        return daten


class DokumentVerschiebenSerializer(serializers.Serializer):
    """Eingabe für das Einsortieren eines Dokuments."""
    register = serializers.UUIDField(
        allow_null=True,
        help_text='Null nimmt das Dokument wieder aus dem Register heraus.',
    )
