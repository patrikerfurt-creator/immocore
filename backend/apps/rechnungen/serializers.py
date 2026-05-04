from rest_framework import serializers
from .models import Kreditor, Rechnung, Freigabe, Verarbeitungslog, RechnungsMatchRegel, RechnungsErkennungsLog


class KreditorSerializer(serializers.ModelSerializer):
    rechnungen_anzahl = serializers.SerializerMethodField()

    class Meta:
        model = Kreditor
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am']

    def get_rechnungen_anzahl(self, obj):
        return obj.rechnungen.count()


class FreigabeSerializer(serializers.ModelSerializer):
    bearbeiter = serializers.HiddenField(default=serializers.CurrentUserDefault())
    bearbeiter_name = serializers.CharField(source='bearbeiter.get_full_name', read_only=True)

    class Meta:
        model = Freigabe
        fields = '__all__'
        read_only_fields = ['id', 'zeitstempel']


class VerarbeitungslogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Verarbeitungslog
        fields = '__all__'
        read_only_fields = ['id', 'zeitpunkt']


class RechnungsMatchRegelSerializer(serializers.ModelSerializer):
    kreditor_name     = serializers.CharField(source='kreditor.name', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    aufwandskonto_label = serializers.SerializerMethodField()
    erstellt_durch_name = serializers.CharField(source='erstellt_durch.get_full_name', read_only=True)

    class Meta:
        model = RechnungsMatchRegel
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am', 'aktualisiert_am']

    def get_aufwandskonto_label(self, obj):
        return f"{obj.aufwandskonto.kontonummer} — {obj.aufwandskonto.kontoname}"


class RechnungsErkennungsLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RechnungsErkennungsLog
        fields = '__all__'
        read_only_fields = ['id', 'zeitpunkt']


class RechnungSerializer(serializers.ModelSerializer):
    kreditor_name          = serializers.CharField(source='kreditor.name', read_only=True)
    lieferant_person_name  = serializers.CharField(source='lieferant.name', read_only=True)
    objekt_bezeichnung     = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    freigaben              = FreigabeSerializer(many=True, read_only=True)
    duplikat_von_dateiname = serializers.CharField(source='duplikat_von.dateiname', read_only=True)
    zugewiesen_an_name     = serializers.CharField(source='zugewiesen_an.get_full_name', read_only=True)
    aufwandskonto_id       = serializers.UUIDField(source='aufwandskonto.id', read_only=True)
    aufwandskonto_label    = serializers.SerializerMethodField()
    darf_direkt_freigeben  = serializers.SerializerMethodField()

    class Meta:
        model = Rechnung
        fields = '__all__'
        read_only_fields = ['id', 'erstellt_am', 'sha256_hash']

    def get_aufwandskonto_label(self, obj):
        if obj.aufwandskonto:
            return f"{obj.aufwandskonto.kontonummer} — {obj.aufwandskonto.kontoname}"
        return None

    def get_darf_direkt_freigeben(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        from .recognition import darf_betreuer_direkt_freigeben
        return darf_betreuer_direkt_freigeben(obj, request.user)


class RechnungListSerializer(serializers.ModelSerializer):
    kreditor_name = serializers.SerializerMethodField()
    duplikat_von_dateiname = serializers.CharField(source='duplikat_von.dateiname', read_only=True)
    objekt_id = serializers.UUIDField(source='objekt.id', read_only=True)
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung', read_only=True)
    vorgeschlagenes_konto_id = serializers.UUIDField(source='vorgeschlagenes_konto.id', read_only=True)
    vorgeschlagenes_konto_label = serializers.SerializerMethodField()
    kostenstelle_id = serializers.UUIDField(source='kostenstelle.id', read_only=True)
    kostenstelle_label = serializers.SerializerMethodField()
    aufwandskonto_id = serializers.UUIDField(source='aufwandskonto.id', read_only=True)
    aufwandskonto_label = serializers.SerializerMethodField()
    zugewiesen_an_id = serializers.UUIDField(source='zugewiesen_an.id', read_only=True)
    zugewiesen_an_name = serializers.CharField(source='zugewiesen_an.get_full_name', read_only=True)
    lock_user = serializers.SerializerMethodField()

    class Meta:
        model = Rechnung
        fields = [
            'id', 'dateiname', 'rechnungsnummer', 'kreditor_name',
            'lieferant_name', 'betrag_brutto', 'waehrung',
            'rechnungsdatum', 'faelligkeitsdatum', 'status',
            'duplikat_typ', 'duplikat_von_dateiname', 'erstellt_am',
            'objekt_id', 'objekt_bezeichnung',
            'kundennummer', 'vorgeschlagenes_konto_id', 'vorgeschlagenes_konto_label',
            'kostenstelle_id', 'kostenstelle_label',
            'erkennungs_stufe', 'erkennungs_konfidenz',
            'aufwandskonto_id', 'aufwandskonto_label',
            'zugewiesen_an_id', 'zugewiesen_an_name',
            'routing_ziel', 'leistungstext',
            'lock_user',
        ]

    def get_kreditor_name(self, obj):
        if obj.kreditor:
            return obj.kreditor.name
        if obj.lieferant:
            return obj.lieferant.name
        return obj.lieferant_name or ''

    def get_vorgeschlagenes_konto_label(self, obj):
        k = obj.vorgeschlagenes_konto
        if not k:
            return None
        return f"{k.kontonummer} — {k.kontoname}"

    def get_kostenstelle_label(self, obj):
        k = obj.kostenstelle
        if not k:
            return None
        return f"{k.kontonummer} — {k.kontoname}"

    def get_aufwandskonto_label(self, obj):
        k = obj.aufwandskonto
        if not k:
            return None
        return f"{k.kontonummer} — {k.kontoname}"

    def get_lock_user(self, obj):
        try:
            lock = obj.bearbeitungslock
            if lock.ist_aktiv:
                return lock.user.get_full_name() or lock.user.username
        except Exception:
            pass
        return None
