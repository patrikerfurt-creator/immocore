from rest_framework import serializers
from .models import (
    Buchungsart, Buchung, Buchungsstapel, OffenerPosten,
    SollstellungsLauf, Sollstellung,
    CamtImportEinstellung, CamtImportLog, ImportOrdnerEinstellung, Kontoumsatz,
    Mahnlauf, Mahnung, Mahnsperre,
    Forderungsfall, Basiszinssatz,
    RAPPosition, RAPAufloesung,
    BankImport, Jahresabrechnung, EinzelAbrechnung,
    LastschriftLauf,
)


class BuchungsartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buchungsart
        fields = '__all__'
        read_only_fields = ['id']


class BuchungSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    soll_konto_nr = serializers.CharField(source='soll_konto.kontonummer', read_only=True)
    soll_konto_name = serializers.CharField(source='soll_konto.kontoname', read_only=True)
    haben_konto_nr = serializers.CharField(source='haben_konto.kontonummer', read_only=True)
    haben_konto_name = serializers.CharField(source='haben_konto.kontoname', read_only=True)
    buchungsart_kuerzel = serializers.CharField(
        source='buchungsart.kuerzel', read_only=True
    )

    class Meta:
        model = Buchung
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am']


class BuchungListSerializer(serializers.ModelSerializer):
    soll_konto_nr = serializers.CharField(source='soll_konto.kontonummer', read_only=True)
    haben_konto_nr = serializers.CharField(source='haben_konto.kontonummer', read_only=True)
    buchungsart_kuerzel = serializers.CharField(
        source='buchungsart.kuerzel', read_only=True
    )

    class Meta:
        model = Buchung
        fields = [
            'id', 'buchungsdatum', 'betrag', 'belegnr',
            'soll_konto_nr', 'haben_konto_nr',
            'buchungstext', 'verwendungszweck',
            'buchungsart_kuerzel', 'status',
        ]


class BuchungsstapelSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    erstellt_von_name = serializers.CharField(source='erstellt_von.username', read_only=True)
    ausgebucht_von_name = serializers.CharField(source='ausgebucht_von.username', read_only=True)
    anzahl_buchungen = serializers.SerializerMethodField()
    gesamt_summe = serializers.SerializerMethodField()

    class Meta:
        model = Buchungsstapel
        fields = [
            'id', 'objekt', 'bezeichnung', 'status',
            'erstellt_von', 'erstellt_von_name', 'erstellt_am',
            'ausgebucht_von_name', 'ausgebucht_am',
            'anzahl_buchungen', 'gesamt_summe',
        ]
        read_only_fields = ['id', 'erstellt_am', 'ausgebucht_am']

    def get_anzahl_buchungen(self, obj):
        return obj.buchungen.count()

    def get_gesamt_summe(self, obj):
        from django.db.models import Sum
        result = obj.buchungen.aggregate(s=Sum('betrag'))['s']
        return float(result) if result else 0.0


class ImportOrdnerEinstellungSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportOrdnerEinstellung
        fields = ['id', 'bereich', 'import_ordner', 'archiv_ordner', 'fehler_ordner', 'aktiv']
        read_only_fields = ['id']


class OffenerPostenSerializer(serializers.ModelSerializer):
    eigentuemer_name = serializers.CharField(
        source='personenkonto.eigentuemer.name', read_only=True
    )
    einheit_nr = serializers.CharField(
        source='personenkonto.vertrag.einheit.einheit_nr', read_only=True
    )

    class Meta:
        model = OffenerPosten
        fields = '__all__'
        read_only_fields = ['id']


class SollstellungsLaufSerializer(serializers.ModelSerializer):
    ausgefuehrt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = SollstellungsLauf
        fields = '__all__'
        read_only_fields = [
            'id', 'erstellt_am', 'anzahl_buchungen',
            'gesamt_summe', 'fehler_log',
        ]


class SollstellungSerializer(serializers.ModelSerializer):
    buchungsart_kuerzel = serializers.CharField(
        source='buchungsart.kuerzel', read_only=True
    )
    eigentuemer_name = serializers.CharField(
        source='personenkonto.eigentuemer.name', read_only=True
    )

    class Meta:
        model = Sollstellung
        fields = '__all__'
        read_only_fields = ['id']


class CamtImportEinstellungSerializer(serializers.ModelSerializer):
    class Meta:
        model = CamtImportEinstellung
        fields = '__all__'
        read_only_fields = ['id', 'zuletzt_geprueft_am', 'letzter_import_am',
                            'letzter_import_datei']


class CamtImportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CamtImportLog
        fields = '__all__'
        read_only_fields = ['id', 'zeitpunkt']


class KontoumsatzSerializer(serializers.ModelSerializer):
    class Meta:
        model = Kontoumsatz
        fields = '__all__'
        read_only_fields = ['id', 'sha256_hash', 'importiert_am', 'ki_vorschlag']


class MahnlaufSerializer(serializers.ModelSerializer):
    ausgefuehrt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Mahnlauf
        fields = '__all__'
        read_only_fields = [
            'id', 'erstellt_am', 'anzahl_mahnungen',
            'gesamt_gebuehren', 'gesamt_zinsen', 'protokoll',
        ]


class MahnungSerializer(serializers.ModelSerializer):
    eigentuemer_name = serializers.CharField(
        source='personenkonto.eigentuemer.name', read_only=True
    )

    class Meta:
        model = Mahnung
        fields = '__all__'
        read_only_fields = ['id']


class MahnsperreSerializer(serializers.ModelSerializer):
    gesetzt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Mahnsperre
        fields = '__all__'
        read_only_fields = ['id', 'gesetzt_am']


class ForderungsfallSerializer(serializers.ModelSerializer):
    eroeffnet_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    gesamtforderung = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    eigentuemer_name = serializers.CharField(
        source='personenkonto.eigentuemer.name', read_only=True
    )

    class Meta:
        model = Forderungsfall
        fields = '__all__'
        read_only_fields = ['id', 'eroeffnet_am']


class BasiszinssatzSerializer(serializers.ModelSerializer):
    class Meta:
        model = Basiszinssatz
        fields = '__all__'
        read_only_fields = ['id']


class RAPPositionSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = RAPPosition
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am']


class RAPAufloesungSerializer(serializers.ModelSerializer):
    class Meta:
        model = RAPAufloesung
        fields = '__all__'
        read_only_fields = ['id']


class BankImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankImport
        fields = '__all__'
        read_only_fields = ['id', 'sha256_hash', 'importiert_am', 'ki_vorschlag']


class JahresabrechnungSerializer(serializers.ModelSerializer):
    erstellt_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Jahresabrechnung
        fields = '__all__'
        read_only_fields = ['id', 'erstellungsdatum']


class EinzelAbrechnungSerializer(serializers.ModelSerializer):
    einheit_nr = serializers.CharField(source='einheit.einheit_nr', read_only=True)

    class Meta:
        model = EinzelAbrechnung
        fields = '__all__'
        read_only_fields = ['id']


class LastschriftLaufSerializer(serializers.ModelSerializer):
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    sollstellungs_lauf_info = serializers.SerializerMethodField()
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta:
        model = LastschriftLauf
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am', 'anzahl_positionen', 'gesamt_summe',
                             'positionen', 'ohne_mandat', 'buchungen_erstellt', 'buchungen_datum']

    def get_sollstellungs_lauf_info(self, obj):
        if not obj.sollstellungs_lauf:
            return None
        lauf = obj.sollstellungs_lauf
        return {
            'id': str(lauf.id),
            'periode_von': str(lauf.periode_von),
            'periode_bis': str(lauf.periode_bis),
            'status': lauf.status,
        }

    def get_erstellt_von_name(self, obj):
        u = obj.erstellt_von
        return u.get_full_name() or u.username
