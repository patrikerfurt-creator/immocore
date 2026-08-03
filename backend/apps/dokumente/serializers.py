from rest_framework import serializers
from .models import Dokument


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
