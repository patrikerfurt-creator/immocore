"""
DRF-Serializer für die Portal-Konto-Endpunkte (Spec Portal-Erweiterung
v1.1, Kap. 6/7).

Eigene, schlanke Serializer statt Wiederverwendung der internen
Personenkonto-/Sollstellungs-Serializer: die internen Serializer
transportieren interne Felder (status_cached, mahnkarenz_bis, opos_nr,
korrektur_grund, ...), die im Portal nichts zu suchen haben.
"""
from rest_framework import serializers

# Portalfreundliche Bezeichnungen statt interner Codes. Reine
# Präsentationslogik (kein Rechenweg) — deshalb hier statt in einem Service,
# aber an einer Stelle gehalten, weil sowohl die Saldo-Aufschlüsselung als
# auch die Fälligkeiten-Liste denselben Text brauchen.
TYP_LABEL = {
    'hausgeld': 'Hausgeld',
    'sonderumlage': 'Sonderumlage',
    'abrechnungsergebnis': 'Abrechnungsergebnis',
    'korrektur': 'Korrektur',
    'saldovortrag': 'Saldovortrag',
}


class AufschluesselungZeileSerializer(serializers.Serializer):
    bezeichnung = serializers.CharField()
    betrag = serializers.DecimalField(max_digits=12, decimal_places=2)


class SaldoSerializer(serializers.Serializer):
    """Serialisiert die in ``PortalSaldoView`` je Personenkonto zusammengestellten
    Dicts — kein Model-Serializer, da die Werte (Saldo, Aufschlüsselung) aus
    dem Saldo-Service stammen und nicht 1:1 an einem Feld hängen."""
    objekt_id = serializers.UUIDField()
    objekt_bezeichnung = serializers.CharField()
    einheit_id = serializers.UUIDField()
    einheit_nr = serializers.CharField()
    kontonummer = serializers.CharField()
    gesamtsaldo = serializers.DecimalField(max_digits=12, decimal_places=2)
    stand_am = serializers.DateTimeField()
    aufschluesselung = AufschluesselungZeileSerializer(many=True)


class FaelligkeitSerializer(serializers.Serializer):
    """Serialisiert `HausgeldSollstellung`-Instanzen — bewusst kein
    ModelSerializer, damit interne Felder (mahnkarenz_bis, opos_nr,
    korrektur_grund, status_cached, Stornofelder) gar nicht erst in der
    Feldliste auftauchen können."""
    objekt_id = serializers.UUIDField()
    objekt_bezeichnung = serializers.CharField(source='objekt.bezeichnung')
    einheit_id = serializers.UUIDField(source='eigentumsverhaeltnis.einheit_id')
    einheit_nr = serializers.CharField(source='eigentumsverhaeltnis.einheit.einheit_nr')
    periode = serializers.DateField()
    bezeichnung = serializers.SerializerMethodField()
    faellig_am = serializers.DateField()
    soll_betrag = serializers.DecimalField(max_digits=12, decimal_places=2)
    offener_betrag = serializers.SerializerMethodField()
    ueberfaellig = serializers.SerializerMethodField()

    def get_bezeichnung(self, obj):
        return TYP_LABEL.get(obj.sollstellungs_typ, obj.sollstellungs_typ)

    def get_offener_betrag(self, obj):
        # str(): SerializerMethodField gibt den Rückgabewert unverändert weiter
        # (anders als DecimalField, das intern auf einen String coerct) —
        # ohne die Umwandlung stünde hier ein Decimal statt des im Contract
        # verlangten Strings mit zwei Nachkommastellen.
        return str(obj.soll_betrag - obj.ist_betrag)

    def get_ueberfaellig(self, obj):
        from django.utils import timezone
        return obj.faellig_am < timezone.localdate()
