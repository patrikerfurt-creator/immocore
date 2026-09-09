from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from .models import Dokument
from .services.beleg_service import loeschsperre_grund as _loeschsperre_grund


class ObjektDokumentSerializer(serializers.ModelSerializer):
    """Schlanker Lese-Serializer für die Dokumentenliste eines Objekts (Spec Abschnitt 7).

    Kein Upload, keine Kategorieverwaltung — nur die Felder für die
    DMS-Leseansicht in ObjektDetail.
    """
    rechnung_nummer = serializers.SerializerMethodField()
    rechnung_id = serializers.SerializerMethodField()

    class Meta:
        model = Dokument
        fields = [
            'id', 'dateiname', 'kategorie', 'dokument_typ', 'abgelegt_am',
            'beleg_nummer', 'revisionssicher', 'rechnung_nummer', 'rechnung_id',
        ]

    def get_rechnung_nummer(self, obj):
        try:
            return obj.rechnung.rechnungsnummer or None
        except ObjectDoesNotExist:
            return None

    def get_rechnung_id(self, obj):
        try:
            return str(obj.rechnung.id)
        except ObjectDoesNotExist:
            return None


KURZTEXT_MAX_LAENGE = 120


class DokumentSerializer(serializers.ModelSerializer):
    """Serializer für die Dokumente-/Belegübersicht.

    Reichert Belege zusätzlich mit den wichtigsten Rechnungsdaten an
    (Belegübersicht-Anreicherung v1.0, siehe API_VERTRAG_BELEGUEBERSICHT_v1_0.md).
    Kein neues DB-Feld nötig — reiner Read-Join über die bestehende
    OneToOne-Relation Rechnung.beleg_dokument (related_name 'rechnung').
    """
    hochgeladen_von = serializers.HiddenField(default=serializers.CurrentUserDefault())
    rechnungsdatum = serializers.SerializerMethodField()
    eingangsdatum = serializers.SerializerMethodField()
    kreditor_name = serializers.SerializerMethodField()
    kreditor_unbestaetigt = serializers.SerializerMethodField()
    betrag_brutto = serializers.SerializerMethodField()
    kurztext = serializers.SerializerMethodField()
    kurztext_volltext = serializers.SerializerMethodField()
    loeschbar = serializers.SerializerMethodField()
    loeschsperre_grund = serializers.SerializerMethodField()

    class Meta:
        model = Dokument
        fields = '__all__'
        # revisionssicher/-_seit, sha256, beleg_nummer, abgelegt_am werden ausschließlich
        # über den beleg_service gesetzt (GoBD) — per API nicht schreibbar.
        read_only_fields = [
            'id', 'hochgeladen_am',
            'revisionssicher', 'revisionssicher_seit', 'sha256', 'beleg_nummer', 'abgelegt_am',
        ]

    def _rechnung(self, obj):
        """Liefert die verknüpfte Rechnung oder None.

        Zentrale Stelle für die Reverse-OneToOne-Auflösung: nur Belege
        (dokument_typ == 'beleg') mit vorhandener Rechnung liefern etwas,
        sonst None (kein RelatedObjectDoesNotExist nach außen).
        """
        if obj.dokument_typ != 'beleg':
            return None
        try:
            return obj.rechnung
        except ObjectDoesNotExist:
            return None

    def get_rechnungsdatum(self, obj):
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        return rechnung.rechnungsdatum

    def get_eingangsdatum(self, obj):
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        return rechnung.erstellt_am

    def get_kreditor_name(self, obj):
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        if rechnung.kreditor_id:
            return rechnung.kreditor.name
        return rechnung.lieferant_name or None

    def get_kreditor_unbestaetigt(self, obj):
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        return rechnung.kreditor_id is None

    def get_betrag_brutto(self, obj):
        """Bruttobetrag als Decimal-String.

        Bewusst str() und nicht der rohe Decimal: DRFs JSON-Encoder wandelt
        Decimal-Werte, die nicht durch ein echtes DecimalField laufen, in
        float um (rest_framework.utils.encoders) — das widerspricht dem
        API-Vertrag und der Konvention 'Decimal für Beträge, kein float'.
        """
        rechnung = self._rechnung(obj)
        if rechnung is None or rechnung.betrag_brutto is None:
            return None
        return str(rechnung.betrag_brutto)

    def get_kurztext(self, obj):
        """Leistungsbeschreibung, auf KURZTEXT_MAX_LAENGE Zeichen gekürzt (inkl. '…')."""
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        text = rechnung.leistungsbeschreibung
        if not text:
            return None
        if len(text) <= KURZTEXT_MAX_LAENGE:
            return text
        return text[:KURZTEXT_MAX_LAENGE - 1] + '…'

    def get_kurztext_volltext(self, obj):
        """Volltext — nur gesetzt, wenn get_kurztext tatsächlich gekürzt hat."""
        rechnung = self._rechnung(obj)
        if rechnung is None:
            return None
        text = rechnung.leistungsbeschreibung
        if not text or len(text) <= KURZTEXT_MAX_LAENGE:
            return None
        return text

    def get_loeschsperre_grund(self, obj):
        """Nutzt beleg_service.loeschsperre_grund als einzige Entscheidungsquelle
        (Nachtrag v1.1) — anders als _rechnung() oben ist hier der Dokumenttyp
        irrelevant, siehe Kommentar in beleg_service.loeschsperre_grund."""
        return _loeschsperre_grund(obj)

    def get_loeschbar(self, obj):
        return _loeschsperre_grund(obj) is None

    def validate(self, attrs):
        # GoBD: Datei und Dokument-Typ dürfen bei einem bestehenden Dokument nicht
        # nachträglich verändert werden (nur bei Neuanlage frei wählbar).
        if self.instance is not None:
            for feld in ('datei', 'dokument_typ'):
                if feld in attrs and attrs[feld] != getattr(self.instance, feld):
                    raise serializers.ValidationError(
                        {feld: f"Das Feld '{feld}' kann bei einem bestehenden Dokument nicht geändert werden."}
                    )
        return attrs
