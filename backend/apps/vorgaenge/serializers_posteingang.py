"""
Serializer für den Mail-Posteingang.

Die Liste zeigt bewusst auch, was die automatische Erkennung VERSUCHT hat
(Person, Objekt, KI-Typ, Konfidenz) — nicht nur, dass sie gescheitert ist.
Ein Bearbeiter entscheidet schneller, wenn er den Vorschlag sieht und nur
noch bestätigen oder korrigieren muss.
"""
from rest_framework import serializers

from apps.vorgaenge.models import MailImportProtokoll


class PosteingangDokumentSerializer(serializers.Serializer):
    """Die zur Mail abgelegten Dokumente — Mail selbst plus Anhänge."""
    id = serializers.UUIDField(read_only=True)
    dateiname = serializers.CharField(read_only=True)
    kategorie = serializers.CharField(read_only=True)
    dokument_typ = serializers.CharField(read_only=True)
    zugeordnet = serializers.SerializerMethodField()

    def get_zugeordnet(self, dokument) -> bool:
        return bool(dokument.objekt_id or dokument.einheit_id
                    or dokument.vorgang_id or dokument.person_id)


class PosteingangSerializer(serializers.ModelSerializer):
    person_name = serializers.SerializerMethodField()
    objekt_bezeichnung = serializers.SerializerMethodField()
    einheit_nr = serializers.SerializerMethodField()
    vorgang_nummer = serializers.SerializerMethodField()
    erledigt_von_name = serializers.SerializerMethodField()
    dokumente = PosteingangDokumentSerializer(many=True, read_only=True)
    status_anzeige = serializers.CharField(source='get_status_display', read_only=True)
    posteingang_status_anzeige = serializers.CharField(
        source='get_posteingang_status_display', read_only=True)

    class Meta:
        model = MailImportProtokoll
        fields = [
            'id', 'dateiname', 'absender', 'absender_name', 'betreff',
            'gesendet_am', 'body_auszug', 'anhaenge_anzahl',
            'status', 'status_anzeige',
            'posteingang_status', 'posteingang_status_anzeige',
            # Was die Erkennung versucht hat — als Entscheidungshilfe.
            'person', 'person_name', 'objekt', 'objekt_bezeichnung',
            'einheit', 'einheit_nr', 'zuordnung_quelle', 'mehrdeutig',
            'personen_treffer',
            'ki_typ_code', 'ki_prioritaet', 'ki_betreff', 'ki_konfidenz',
            'ki_begruendung',
            'vorgang', 'vorgang_nummer',
            'erledigt_am', 'erledigt_von_name', 'erledigt_notiz',
            'dokumente', 'verarbeitet_am',
        ]
        read_only_fields = fields

    def get_person_name(self, obj):
        return obj.person.name if obj.person_id else None

    def get_objekt_bezeichnung(self, obj):
        return obj.objekt.bezeichnung if obj.objekt_id else None

    def get_einheit_nr(self, obj):
        return obj.einheit.einheit_nr if obj.einheit_id else None

    def get_vorgang_nummer(self, obj):
        return obj.vorgang.nummer if obj.vorgang_id else None

    def get_erledigt_von_name(self, obj):
        if not obj.erledigt_von_id:
            return None
        benutzer = obj.erledigt_von
        return benutzer.get_full_name() or benutzer.username


class VorgangAnlegenSerializer(serializers.Serializer):
    """Eingabe für ``vorgang-anlegen``."""
    typ = serializers.UUIDField()
    objekt = serializers.UUIDField(required=False, allow_null=True)
    einheit = serializers.UUIDField(required=False, allow_null=True)
    person = serializers.UUIDField(required=False, allow_null=True)
    betreff = serializers.CharField(required=False, allow_blank=True, max_length=200)
    prioritaet = serializers.ChoiceField(
        choices=['niedrig', 'normal', 'hoch'], required=False, allow_blank=True)
    notiz = serializers.CharField(required=False, allow_blank=True)

    def validate(self, daten):
        if not any(daten.get(f) for f in ('objekt', 'einheit', 'person')):
            raise serializers.ValidationError(
                'Mindestens eines von Objekt, Einheit oder Person ist nötig — '
                'ein Vorgang ohne Bezug ist nicht auswertbar.'
            )
        return daten


class VorgangZuordnenSerializer(serializers.Serializer):
    vorgang = serializers.UUIDField()
    notiz = serializers.CharField(required=False, allow_blank=True)


class NurAblegenSerializer(serializers.Serializer):
    objekt = serializers.UUIDField(required=False, allow_null=True)
    einheit = serializers.UUIDField(required=False, allow_null=True)
    person = serializers.UUIDField(required=False, allow_null=True)
    notiz = serializers.CharField(required=False, allow_blank=True)

    def validate(self, daten):
        gesetzt = [f for f in ('objekt', 'einheit', 'person') if daten.get(f)]
        if len(gesetzt) != 1:
            raise serializers.ValidationError(
                'Genau ein Kontext (Objekt, Einheit oder Person) muss '
                'angegeben werden.'
            )
        return daten


class VerwerfenSerializer(serializers.Serializer):
    # Pflicht: nach dem Löschen der Dokumente ist die Notiz die einzige Spur.
    notiz = serializers.CharField(allow_blank=False)
