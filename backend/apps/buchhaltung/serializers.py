from rest_framework import serializers
from apps.objekte.models import Wirtschaftsjahr, EinheitVerbrauch
from apps.konten.models import KontoVerteilerSchluessel
from .models import (
    Buchungsart, Buchung, Buchungsstapel, OffenerPosten, KreditorOP,
    CamtImportEinstellung, CamtImportLog, ImportOrdnerEinstellung, Kontoumsatz,
    BankMatchRegel, BankErkennungsLog,
    Mahnlauf, Mahnung, Mahnsperre,
    Forderungsfall, Basiszinssatz,
    RAPPosition, RAPAufloesung,
    BankImport, Jahresabrechnung, EinzelAbrechnung,
    LastschriftLauf,
    HausgeldSollstellungslauf, HausgeldSollstellung, SollstellungSplit,
    AutoLaufProtokoll,
)


class WirtschaftsjahrSerializer(serializers.ModelSerializer):
    beginn_datum   = serializers.DateField(read_only=True)
    ende_datum     = serializers.DateField(read_only=True)
    objekt_nr      = serializers.CharField(source='objekt.objektnummer', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)

    class Meta:
        model = Wirtschaftsjahr
        fields = [
            'id', 'objekt', 'objekt_nr', 'objekt_bezeichnung',
            'jahr', 'beginn_monat', 'status',
            'vorjahr', 'eroeffnet_am', 'eroeffnet_von',
            'abgeschlossen_am', 'beginn_datum', 'ende_datum',
        ]
        read_only_fields = ['id', 'eroeffnet_am', 'abgeschlossen_am']


class KontoVerteilerSchluesselSerializer(serializers.ModelSerializer):
    class Meta:
        model  = KontoVerteilerSchluessel
        fields = '__all__'
        read_only_fields = ['id']


class EinheitVerbrauchSerializer(serializers.ModelSerializer):
    class Meta:
        model  = EinheitVerbrauch
        fields = '__all__'
        read_only_fields = ['id']


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


class KreditorOPSerializer(serializers.ModelSerializer):
    kreditor_name = serializers.SerializerMethodField()
    rechnung_nr   = serializers.SerializerMethodField()
    betreff       = serializers.SerializerMethodField()

    def get_kreditor_name(self, obj):
        k = obj.kreditor
        return k.name if k else ''

    def get_rechnung_nr(self, obj):
        return obj.rechnung.rechnungsnummer if obj.rechnung else ''

    def get_betreff(self, obj):
        if obj.rechnung:
            return getattr(obj.rechnung, 'betreff', '') or ''
        return ''

    class Meta:
        model  = KreditorOP
        fields = [
            'id', 'op_nummer',
            'betrag_ursprung', 'betrag_offen', 'faellig_ab', 'status',
            'kreditor_name', 'rechnung_nr', 'betreff',
        ]


# ---------------------------------------------------------------------------
# E-Banking Phase E — BankBuchung + BankMatchRegel
# ---------------------------------------------------------------------------

class _KontoInlineSerializer(serializers.Serializer):
    id             = serializers.UUIDField()
    kontonummer    = serializers.CharField()
    kontoname      = serializers.CharField()


class _PersonInlineSerializer(serializers.Serializer):
    id         = serializers.UUIDField()
    name       = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.firmenname or f"{obj.vorname or ''} {obj.nachname or ''}".strip()


class _EVInlineSerializer(serializers.Serializer):
    id             = serializers.UUIDField()
    einheit_nr     = serializers.CharField(source='einheit.einheit_nr')
    eigentuemer    = serializers.SerializerMethodField()

    def get_eigentuemer(self, obj):
        p = getattr(obj, 'person', None)
        if not p:
            return ''
        return p.firmenname or f"{p.vorname or ''} {p.nachname or ''}".strip()


class BankErkennungsLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BankErkennungsLog
        fields = [
            'id', 'stufe_erreicht', 'quelle', 'konfidenz',
            'auto_verbucht', 'details_json', 'erstellt_am',
        ]


class BankBuchungSerializer(serializers.ModelSerializer):
    erkannt_gegenkonto_detail    = _KontoInlineSerializer(source='erkannt_gegenkonto', read_only=True)
    erkannt_kreditor_detail      = _PersonInlineSerializer(source='erkannt_kreditor', read_only=True)
    erkannt_eigentumsverh_detail = _EVInlineSerializer(source='erkannt_eigentumsverhaeltnis', read_only=True)
    verbucht_von_username        = serializers.CharField(source='verbucht_von.username', read_only=True)
    erkennungs_log               = BankErkennungsLogSerializer(
        source='erkennungs_logs', many=True, read_only=True,
    )

    class Meta:
        model  = Kontoumsatz
        fields = [
            'id', 'objekt', 'bankkonto', 'sha256_hash',
            'betrag', 'buchungsdatum', 'wertstellungsdatum',
            'auftraggeber_name', 'auftraggeber_iban', 'empfaenger_iban',
            'verwendungszweck', 'end_to_end_id',
            'status',
            'erkannt_gegenkonto', 'erkannt_gegenkonto_detail',
            'erkannt_eigentumsverhaeltnis', 'erkannt_eigentumsverh_detail',
            'erkannt_kreditor', 'erkannt_kreditor_detail',
            'erkennungs_quelle', 'erkennungs_konfidenz', 'erkennungs_begruendung',
            'match_regel',
            'buchung', 'verbucht_am', 'verbucht_von', 'verbucht_von_username',
            'notiz', 'importiert_am', 'import_datei',
            'erkennungs_log',
        ]
        read_only_fields = [
            'id', 'sha256_hash', 'importiert_am',
            'buchung', 'verbucht_am', 'verbucht_von',
            'erkennungs_quelle', 'erkennungs_konfidenz', 'erkennungs_begruendung',
            'erkannt_gegenkonto_detail', 'erkannt_kreditor_detail',
            'erkannt_eigentumsverh_detail', 'verbucht_von_username',
            'erkennungs_log',
        ]


class BankMatchRegelSerializer(serializers.ModelSerializer):
    gegenkonto_detail    = _KontoInlineSerializer(source='gegenkonto', read_only=True)
    bankkonto_iban       = serializers.CharField(source='bankkonto.iban', read_only=True)
    erstellt_von_username = serializers.CharField(source='erstellt_von.username', read_only=True)

    class Meta:
        model  = BankMatchRegel
        fields = [
            'id', 'bankkonto', 'bankkonto_iban',
            'kontrahent_iban', 'verwendungszweck_hash',
            'gegenkonto', 'gegenkonto_detail',
            'kreditor', 'eigentumsverhaeltnis',
            'status', 'erstellt_aus', 'trefferzahl',
            'letzte_anwendung', 'erstellt_am',
            'erstellt_von', 'erstellt_von_username',
        ]
        read_only_fields = [
            'id', 'bankkonto', 'kontrahent_iban', 'verwendungszweck_hash',
            'gegenkonto', 'kreditor', 'eigentumsverhaeltnis',
            'erstellt_aus', 'trefferzahl', 'letzte_anwendung',
            'erstellt_am', 'erstellt_von',
            'bankkonto_iban', 'gegenkonto_detail', 'erstellt_von_username',
        ]


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
    objekt_bezeichnung  = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    hausgeld_lauf_info  = serializers.SerializerMethodField()
    erstellt_von_name   = serializers.SerializerMethodField()

    class Meta:
        model = LastschriftLauf
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am', 'anzahl_positionen', 'gesamt_summe',
                             'positionen', 'ohne_mandat', 'buchungen_erstellt', 'buchungen_datum']

    def get_hausgeld_lauf_info(self, obj):
        lauf = obj.hausgeld_sollstellungslauf
        if not lauf:
            return None
        return {
            'id': str(lauf.id),
            'periode': str(lauf.periode),
            'status': lauf.status,
            'anzahl_sollstellungen': lauf.anzahl_sollstellungen,
        }

    def get_erstellt_von_name(self, obj):
        u = obj.erstellt_von
        return u.get_full_name() or u.username


# ---------------------------------------------------------------------------
# Hausgeld-Nebenbuch Serializers
# ---------------------------------------------------------------------------

class SollstellungSplitSerializer(serializers.ModelSerializer):
    ba_nr          = serializers.CharField(source='ba.nr', read_only=True)
    ba_bezeichnung = serializers.CharField(source='ba.bezeichnung', read_only=True)

    class Meta:
        model  = SollstellungSplit
        fields = ['id', 'ba', 'ba_nr', 'ba_bezeichnung', 'betrag', 'ist_betrag_split', 'bankkonto_ziel', 'erloeskonto']


class HausgeldSollstellungListSerializer(serializers.ModelSerializer):
    status              = serializers.CharField(read_only=True)
    ev_person_name      = serializers.SerializerMethodField()
    ev_einheit_nr       = serializers.SerializerMethodField()
    objekt_bezeichnung  = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    ba_nr               = serializers.CharField(source='ba.nr', read_only=True)
    personenkonto_id    = serializers.SerializerMethodField()
    personenkonto_nr    = serializers.SerializerMethodField()

    class Meta:
        model  = HausgeldSollstellung
        fields = [
            'id', 'objekt', 'objekt_bezeichnung',
            'eigentumsverhaeltnis', 'ev_person_name', 'ev_einheit_nr',
            'personenkonto_id', 'personenkonto_nr',
            'sollstellungs_typ', 'ba', 'ba_nr',
            'periode', 'faellig_am', 'opos_nr',
            'soll_betrag', 'ist_betrag', 'status', 'status_cached',
            'storniert_am', 'erstellt_am',
        ]

    def get_ev_person_name(self, obj):
        try:
            return obj.eigentumsverhaeltnis.person.name
        except Exception:
            return None

    def get_ev_einheit_nr(self, obj):
        try:
            return obj.eigentumsverhaeltnis.einheit.einheitennummer
        except Exception:
            return None

    def get_personenkonto_id(self, obj):
        try:
            return str(obj.eigentumsverhaeltnis.personenkonto.id)
        except Exception:
            return None

    def get_personenkonto_nr(self, obj):
        try:
            return obj.eigentumsverhaeltnis.personenkonto.kontonummer
        except Exception:
            return None


class HausgeldSollstellungSerializer(HausgeldSollstellungListSerializer):
    splits         = SollstellungSplitSerializer(many=True, read_only=True)
    erstellt_von_name = serializers.SerializerMethodField()

    class Meta(HausgeldSollstellungListSerializer.Meta):
        fields = HausgeldSollstellungListSerializer.Meta.fields + [
            'splits', 'sollstellungslauf', 'storniert_grund', 'erstellt_von', 'erstellt_von_name',
        ]

    def get_erstellt_von_name(self, obj):
        try:
            u = obj.erstellt_von
            return u.get_full_name() or u.username
        except Exception:
            return None


class HausgeldSollstellungslaufSerializer(serializers.ModelSerializer):
    objekt_bezeichnung  = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    erstellt_von_name   = serializers.SerializerMethodField()
    freigabe_user_name  = serializers.SerializerMethodField()

    class Meta:
        model  = HausgeldSollstellungslauf
        fields = [
            'id', 'objekt', 'objekt_bezeichnung', 'typ', 'periode', 'status',
            'anzahl_sollstellungen', 'summe', 'fehler_details',
            'erstellt_am', 'erstellt_von', 'erstellt_von_name',
            'freigabe_user', 'freigabe_user_name', 'freigegeben_am',
            'commited_am', 'storniert_am', 'storniert_grund',
        ]
        read_only_fields = ['id', 'erstellt_am', 'commited_am', 'freigegeben_am']

    def get_erstellt_von_name(self, obj):
        try:
            u = obj.erstellt_von
            return u.get_full_name() or u.username
        except Exception:
            return None

    def get_freigabe_user_name(self, obj):
        try:
            u = obj.freigabe_user
            return u.get_full_name() or u.username if u else None
        except Exception:
            return None


class AutoLaufProtokollSerializer(serializers.ModelSerializer):
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    objekt_nummer      = serializers.CharField(source='objekt.objektnummer', read_only=True)

    class Meta:
        model  = AutoLaufProtokoll
        fields = [
            'id', 'objekt', 'objekt_bezeichnung', 'objekt_nummer',
            'ausgefuehrt_am', 'periode', 'status',
            'sollstellungslauf', 'lastschriftlauf',
            'anzahl_evs_geplant', 'anzahl_evs_erfolgreich', 'anzahl_evs_uebersprungen',
            'summe_sollstellungen', 'summe_lastschrift',
            'datei_pfad', 'warnungen', 'fehler',
        ]
        read_only_fields = [
            'id', 'ausgefuehrt_am', 'periode', 'status',
            'sollstellungslauf', 'lastschriftlauf',
            'anzahl_evs_geplant', 'anzahl_evs_erfolgreich', 'anzahl_evs_uebersprungen',
            'summe_sollstellungen', 'summe_lastschrift',
            'datei_pfad', 'warnungen', 'fehler',
        ]
