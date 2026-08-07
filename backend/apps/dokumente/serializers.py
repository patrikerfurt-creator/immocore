from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from .models import Dokument


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


class DokumentSerializer(serializers.ModelSerializer):
    hochgeladen_von = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Dokument
        fields = '__all__'
        # revisionssicher/-_seit, sha256, beleg_nummer, abgelegt_am werden ausschließlich
        # über den beleg_service gesetzt (GoBD) — per API nicht schreibbar.
        read_only_fields = [
            'id', 'hochgeladen_am',
            'revisionssicher', 'revisionssicher_seit', 'sha256', 'beleg_nummer', 'abgelegt_am',
        ]

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
