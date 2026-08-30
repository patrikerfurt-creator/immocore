from rest_framework import serializers

from .models import KreditorBankverbindung, KreditorDublettenPruefung


class KreditorBankverbindungSerializer(serializers.ModelSerializer):
    class Meta:
        model = KreditorBankverbindung
        fields = ['id', 'kreditor', 'iban', 'bic', 'bemerkung', 'aktiv', 'erfasst_am']
        read_only_fields = ['id', 'erfasst_am']


class KreditorDublettenPruefungSerializer(serializers.ModelSerializer):
    """Alles, was die Prüfoberfläche für eine Entscheidung braucht.

    ``kandidaten`` kommt unverändert aus dem JSONField — es ist der zum
    Prüfzeitpunkt eingefrorene Stand, nicht eine frische Abfrage. Genau
    das macht die Entscheidung später nachvollziehbar.
    """

    anlass_text = serializers.CharField(source='get_anlass_display', read_only=True)
    status_text = serializers.CharField(source='get_status_display', read_only=True)
    rechnung_dateiname = serializers.CharField(source='rechnung.dateiname', read_only=True)
    rechnungsnummer = serializers.CharField(source='rechnung.rechnungsnummer', read_only=True)
    rechnungsdatum = serializers.DateField(source='rechnung.rechnungsdatum', read_only=True)
    betrag_brutto = serializers.DecimalField(
        source='rechnung.betrag_brutto', max_digits=12, decimal_places=2,
        read_only=True, allow_null=True,
    )
    entschieden_von_name = serializers.SerializerMethodField()
    ergebnis_kreditor_name = serializers.CharField(
        source='ergebnis_kreditor.name', read_only=True, default='',
    )

    class Meta:
        model = KreditorDublettenPruefung
        fields = [
            'id', 'rechnung', 'rechnung_dateiname', 'rechnungsnummer',
            'rechnungsdatum', 'betrag_brutto',
            'erkannter_name', 'erkannte_iban',
            'anlass', 'anlass_text', 'kandidaten',
            'status', 'status_text', 'notiz',
            'ergebnis_kreditor', 'ergebnis_kreditor_name',
            'entschieden_von', 'entschieden_von_name', 'entschieden_am',
            'erstellt_am',
        ]
        read_only_fields = fields

    def get_entschieden_von_name(self, obj) -> str:
        if obj.entschieden_von is None:
            return ''
        return obj.entschieden_von.get_full_name() or obj.entschieden_von.username
