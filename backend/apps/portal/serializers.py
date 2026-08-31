"""
Serializer des Eigentümer-Portals (Spec 1a).

Bewusst schlanke, explizite Serializer statt ``ModelSerializer`` auf
``Person``: ein ModelSerializer würde bei jedem künftigen Feld auf
``Person`` automatisch mehr Daten ins Portal durchreichen. Hier ist die
Feldliste die Sicherheitsgrenze, deshalb steht sie ausgeschrieben da.
"""
from rest_framework import serializers


class MagicLinkAnfrageSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class MeineDatenSerializer(serializers.Serializer):
    """Read-only-Sicht auf die eigenen Stammdaten (Spec Kap. 6.2)."""

    person_id = serializers.UUIDField(read_only=True)
    personennummer = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    anrede = serializers.CharField(read_only=True)
    strasse = serializers.CharField(read_only=True)
    hausnummer = serializers.CharField(read_only=True)
    plz = serializers.CharField(read_only=True)
    ort = serializers.CharField(read_only=True)
    telefon = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    email_pending = serializers.CharField(read_only=True)
    iban = serializers.CharField(read_only=True)
    bic = serializers.CharField(read_only=True)
    hat_aktives_mandat = serializers.BooleanField(read_only=True)
    mandatsreferenz = serializers.CharField(read_only=True, allow_null=True)


class KontaktAenderungSerializer(serializers.Serializer):
    """PATCH auf Adresse/Telefon.

    ``required=False`` auf allen Feldern, damit eine Teiländerung möglich
    ist; ``validate`` stellt sicher, dass überhaupt etwas übergeben wurde.
    Name und Geburtsdatum sind bewusst nicht enthalten — identitäts-
    relevante Stammdaten bleiben Verwaltungssache (Spec Kap. 1.2).

    ``Person.adresse`` (der zusammengesetzte Textblock) ist bewusst NICHT
    beschreibbar — er entsteht in ``Person.save()`` aus den Einzelfeldern.
    """

    strasse = serializers.CharField(required=False, allow_blank=True, max_length=255)
    hausnummer = serializers.CharField(required=False, allow_blank=True, max_length=20)
    plz = serializers.CharField(required=False, allow_blank=True, max_length=10)
    ort = serializers.CharField(required=False, allow_blank=True, max_length=100)
    telefon = serializers.CharField(required=False, allow_blank=True, max_length=50)

    def validate_plz(self, wert):
        wert = (wert or '').strip()
        if wert and not (wert.isdigit() and 4 <= len(wert) <= 5):
            raise serializers.ValidationError('Bitte eine gültige Postleitzahl angeben.')
        return wert

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Keine Änderungen übergeben.')
        return attrs


class BankverbindungSerializer(serializers.Serializer):
    """PATCH auf IBAN/BIC.

    Kein ``kontoinhaber``: das Feld existiert im realen Datenmodell weder
    auf ``Person`` noch auf ``SEPAMandat`` (siehe stammdaten_service).
    """

    iban = serializers.CharField(required=False, allow_blank=False, max_length=34)
    bic = serializers.CharField(required=False, allow_blank=True, max_length=11)

    def validate_iban(self, wert):
        roh = (wert or '').replace(' ', '').strip().upper()
        try:
            from schwifty import IBAN
            IBAN(roh)
        except ImportError:
            # Ohne schwifty keine Prüfung erzwingen — das Backend soll bei
            # fehlender optionaler Abhängigkeit nicht ausfallen.
            pass
        except Exception:
            raise serializers.ValidationError('Diese IBAN ist ungültig.')
        return roh

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Keine Änderungen übergeben.')
        return attrs


class EmailAenderungSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EinheitSerializer(serializers.Serializer):
    einheit_id = serializers.UUIDField()
    einheit_nr = serializers.CharField()
    lage = serializers.CharField()
    nutzungsart = serializers.CharField()
    miteigentumsanteil = serializers.DecimalField(
        max_digits=12, decimal_places=4, allow_null=True,
    )
    eigentum_seit = serializers.DateField()
    eigentum_bis = serializers.DateField(allow_null=True)


class WegKarteSerializer(serializers.Serializer):
    objekt_id = serializers.UUIDField()
    objektnummer = serializers.CharField()
    bezeichnung = serializers.CharField()
    strasse = serializers.CharField()
    plz = serializers.CharField()
    ort = serializers.CharField()
    einheiten = EinheitSerializer(many=True)


class PortalZugangVerwaltungSerializer(serializers.Serializer):
    """Sicht der Verwaltung auf den Zugang einer Person (interner Bereich)."""

    id = serializers.UUIDField(read_only=True)
    person_id = serializers.UUIDField(source='person.id', read_only=True)
    person_name = serializers.CharField(source='person.name', read_only=True)
    email = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    aktiv = serializers.BooleanField(read_only=True)
    eingeladen_am = serializers.DateTimeField(read_only=True)
    eingeladen_von = serializers.SerializerMethodField()
    erstaktivierung_am = serializers.DateTimeField(read_only=True, allow_null=True)
    letzter_login = serializers.DateTimeField(read_only=True, allow_null=True)
    email_pending = serializers.CharField(read_only=True)

    def get_email(self, zugang) -> str:
        from .services import zugang_service
        return zugang_service.person_email(zugang.person)

    def get_eingeladen_von(self, zugang) -> str:
        if zugang.eingeladen_von is None:
            return ''
        return zugang.eingeladen_von.user.get_full_name() or zugang.eingeladen_von.user.username
