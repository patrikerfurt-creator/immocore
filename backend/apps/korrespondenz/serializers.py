"""Serializer des Moduls Vorlagen & Korrespondenz (Phase 4: Schreiben, Druckstapel, Serienlauf;
Phase 5a: Vorlagen, Versionen, Textbausteine, Briefbögen, Vorschau, KI-Assistent).

Nur Ein-/Ausgabeformate - keine Geschäftslogik (liegt in ``services/``).
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.objekte.models import Einheit, Objekt
from apps.personen.models import EigentumsVerhaeltnis, Person
from apps.vorgaenge.models import Vorgang

from .models import (
    Briefbogen, Druckstapel, Schreiben, Serienlauf, Textbaustein, Vorlage, VorlagenVersion,
)
from .services import (
    blockstruktur_service, eingabefelder_service, kanal_service, registry, schreiben_service,
    serienlauf_service, vorlage_service,
)

User = get_user_model()


def _ref(obj, **felder):
    """``{id, ...}`` eines optionalen Objekts, sonst ``None``."""
    if obj is None:
        return None
    return {'id': str(obj.pk), **{name: getter(obj) for name, getter in felder.items()}}


def _nicht_erzeugbar(schreiben) -> bool:
    return schreiben.status == 'entwurf' and bool(schreiben.fehler)


class SchreibenListSerializer(serializers.ModelSerializer):
    status_anzeige = serializers.CharField(source='get_status_display', read_only=True)
    nicht_erzeugbar = serializers.SerializerMethodField()
    betreff = serializers.SerializerMethodField()
    vorlage = serializers.SerializerMethodField()
    einzeln_bearbeitbar = serializers.BooleanField(
        source='vorlage_version.vorlage.einzeln_bearbeitbar', read_only=True)
    empfaenger = serializers.SerializerMethodField()
    objekt = serializers.SerializerMethodField()
    einheit = serializers.SerializerMethodField()
    auch_brief = serializers.SerializerMethodField()

    class Meta:
        model = Schreiben
        fields = [
            'id', 'nummer', 'status', 'status_anzeige', 'nicht_erzeugbar', 'fehler', 'kanal',
            'auch_brief', 'betreff', 'vorlage', 'einzeln_bearbeitbar', 'empfaenger', 'objekt',
            'einheit', 'serienlauf', 'vorgang', 'dokument', 'druckstapel', 'erstellt_am',
            'freigegeben_am', 'versendet_am',
        ]
        read_only_fields = fields

    def get_nicht_erzeugbar(self, obj):
        return _nicht_erzeugbar(obj)

    def get_betreff(self, obj):
        return (obj.kontext_snapshot or {}).get(schreiben_service.SNAPSHOT_BETREFF, '')

    def get_vorlage(self, obj):
        v = obj.vorlage_version.vorlage
        return {'id': str(v.pk), 'code': v.code, 'bezeichnung': v.bezeichnung, 'anlass': v.anlass}

    def get_empfaenger(self, obj):
        return _ref(obj.empfaenger, name=lambda p: p.name)

    def get_objekt(self, obj):
        return _ref(obj.objekt, bezeichnung=lambda o: o.bezeichnung)

    def get_einheit(self, obj):
        return _ref(obj.einheit, einheit_nr=lambda e: e.einheit_nr)

    def get_auch_brief(self, obj):
        return kanal_service.auch_brief(obj)


class SchreibenDetailSerializer(SchreibenListSerializer):
    vorlage_version_info = serializers.SerializerMethodField()

    class Meta(SchreibenListSerializer.Meta):
        fields = SchreibenListSerializer.Meta.fields + [
            'html_gerendert', 'inhalt_angepasst', 'eingabewerte', 'ihr_zeichen',
            'ihr_schreiben_vom', 'unterzeichner', 'mail_message_id', 'freigegeben_von',
            'vorlage_version', 'vorlage_version_info',
        ]
        read_only_fields = fields

    def get_vorlage_version_info(self, obj):
        """Version, aus der das Schreiben erzeugt wurde (Ausgangstext der Einzelanpassung: ``GET /versionen/{id}/``)."""
        v = obj.vorlage_version
        return {
            'id': str(v.pk), 'version': v.version, 'status': v.status, 'betreff': v.betreff,
            'vorlage_id': str(v.vorlage_id), 'vorlage_code': v.vorlage.code,
            'vorlage_bezeichnung': v.vorlage.bezeichnung,
        }


class SchreibenCreateSerializer(serializers.Serializer):
    """Eingabe für ``POST /schreiben/`` (Mahnung/Eigentümerwechsel folgen mit Phase 6)."""
    vorlage_code = serializers.CharField(max_length=50)
    empfaenger = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all())
    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all(), required=False, allow_null=True)
    einheit = serializers.PrimaryKeyRelatedField(queryset=Einheit.objects.all(), required=False, allow_null=True)
    eigentumsverhaeltnis = serializers.PrimaryKeyRelatedField(
        queryset=EigentumsVerhaeltnis.objects.all(), required=False, allow_null=True)
    vorgang = serializers.PrimaryKeyRelatedField(queryset=Vorgang.objects.all(), required=False, allow_null=True)
    eingabewerte = serializers.DictField(required=False)
    kanal = serializers.ChoiceField(choices=['brief', 'email', 'beides'], required=False, allow_null=True)
    unterzeichner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    ihr_zeichen = serializers.CharField(max_length=100, required=False, allow_blank=True)
    ihr_schreiben_vom = serializers.DateField(required=False, allow_null=True)


class SchreibenAnpassenSerializer(serializers.Serializer):
    """Eingabe für ``PATCH /schreiben/{id}/`` (Textanpassung)."""
    inhalt_angepasst = serializers.ListField(child=serializers.DictField())


class SchreibenVersendenSerializer(serializers.Serializer):
    kanal = serializers.ChoiceField(choices=['brief'], required=False, allow_null=True)


class DruckstapelCreateSerializer(serializers.Serializer):
    schreiben_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all(), required=False, allow_null=True)


class DruckstapelSerializer(serializers.ModelSerializer):
    anzahl = serializers.SerializerMethodField()
    schreiben = serializers.SerializerMethodField()
    status_anzeige = serializers.CharField(source='get_status_display', read_only=True)
    dokument_info = serializers.SerializerMethodField()

    class Meta:
        model = Druckstapel
        fields = ['id', 'status', 'status_anzeige', 'dokument', 'dokument_info', 'anzahl',
                  'schreiben', 'erstellt_am', 'erstellt_von', 'bestaetigt_am', 'bestaetigt_von']
        read_only_fields = fields

    def _schreiben(self, obj):
        # ``.all()`` nutzt einen Prefetch der Liste; ohne Prefetch genau eine Abfrage.
        return sorted(obj.schreiben.all(), key=lambda s: s.nummer)

    def get_anzahl(self, obj):
        return len(obj.schreiben.all())

    def get_dokument_info(self, obj):
        return _ref(obj.dokument, dateiname=lambda d: d.dateiname, titel=lambda d: d.titel)

    def get_schreiben(self, obj):
        return [
            {
                'id': str(s.pk), 'nummer': s.nummer, 'status': s.status,
                'empfaenger': _ref(s.empfaenger, name=lambda p: p.name),
                'objekt': _ref(s.objekt, bezeichnung=lambda o: o.bezeichnung),
            }
            for s in self._schreiben(obj)
        ]


class SerienlaufCreateSerializer(serializers.Serializer):
    vorlage_version = serializers.UUIDField(required=False)
    vorlage_code = serializers.CharField(max_length=50, required=False)
    objekt = serializers.PrimaryKeyRelatedField(queryset=Objekt.objects.all())
    empfaenger_filter = serializers.DictField(required=False)
    eingabewerte = serializers.DictField(required=False)
    unterzeichner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)

    def validate(self, attrs):
        if bool(attrs.get('vorlage_version')) == bool(attrs.get('vorlage_code')):
            raise serializers.ValidationError('Genau eines von "vorlage_version" oder "vorlage_code" angeben.')
        return attrs


class SerienlaufDetailSerializer(serializers.ModelSerializer):
    status_anzeige = serializers.CharField(source='get_status_display', read_only=True)
    vorlage = serializers.SerializerMethodField()
    objekt = serializers.SerializerMethodField()
    zaehler = serializers.SerializerMethodField()
    vorschau = serializers.SerializerMethodField()
    nicht_erzeugbar = serializers.SerializerMethodField()
    blocker = serializers.SerializerMethodField()
    freigebbar = serializers.SerializerMethodField()
    druckstapel_ids = serializers.SerializerMethodField()

    class Meta:
        model = Serienlauf
        fields = [
            'id', 'status', 'status_anzeige', 'vorlage_version', 'vorlage', 'objekt',
            'empfaenger_filter', 'eingabewerte', 'unterzeichner', 'anzahl', 'zaehler',
            'vorschau', 'nicht_erzeugbar', 'freigebbar', 'blocker', 'druck_dokument',
            'druckstapel_ids', 'erstellt_am', 'freigegeben_am',
        ]
        read_only_fields = fields

    def _vorschau(self, obj):
        # Pro Serialisierung nur einmal berechnen.
        if not hasattr(self, '_vorschau_cache'):
            self._vorschau_cache = {}
        if obj.pk not in self._vorschau_cache:
            self._vorschau_cache[obj.pk] = serienlauf_service.vorschau(obj)
        return self._vorschau_cache[obj.pk]

    def get_vorlage(self, obj):
        v = obj.vorlage_version.vorlage
        return {'id': str(v.pk), 'code': v.code, 'bezeichnung': v.bezeichnung, 'anlass': v.anlass}

    def get_objekt(self, obj):
        return _ref(obj.objekt, bezeichnung=lambda o: o.bezeichnung)

    def get_zaehler(self, obj):
        je_status = {}
        for status in obj.schreiben.values_list('status', flat=True):
            je_status[status] = je_status.get(status, 0) + 1
        return {
            'gesamt': sum(je_status.values()),
            'nicht_erzeugbar': len(self._vorschau(obj).nicht_erzeugbar),
            'je_status': je_status,
        }

    def get_vorschau(self, obj):
        v = self._vorschau(obj)
        return {
            'erzeugbar_anzahl': v.erzeugbar_anzahl,
            'zufaellig': [
                {
                    'schreiben_id': str(s.pk), 'nummer': s.nummer,
                    'empfaenger': s.empfaenger.name,
                    'einheit_nr': s.einheit.einheit_nr if s.einheit_id else '',
                    'betreff': (s.kontext_snapshot or {}).get(schreiben_service.SNAPSHOT_BETREFF, ''),
                    'html_gerendert': s.html_gerendert,
                }
                for s in v.zufaellig
            ],
        }

    def get_nicht_erzeugbar(self, obj):
        return [
            {
                'schreiben_id': str(s.pk), 'nummer': s.nummer, 'empfaenger': s.empfaenger.name,
                'einheit_nr': s.einheit.einheit_nr if s.einheit_id else '', 'ursache': s.fehler,
            }
            for s in self._vorschau(obj).nicht_erzeugbar
        ]

    def get_blocker(self, obj):
        return serienlauf_service.freigabe_blocker(obj) if obj.status == 'zur_pruefung' else []

    def get_freigebbar(self, obj):
        return obj.status == 'zur_pruefung' and not serienlauf_service.freigabe_blocker(obj)

    def get_druckstapel_ids(self, obj):
        return [
            str(i) for i in obj.schreiben.exclude(druckstapel__isnull=True)
            .order_by().values_list('druckstapel', flat=True).distinct()
        ]


# --------------------------------------------------------------------------
# Phase 5a: Vorlagen-Editor
# --------------------------------------------------------------------------

class VorlagenVersionSerializer(serializers.ModelSerializer):
    """Version einer Vorlage. Schreibbar (PATCH, nur ``entwurf``) sind die Inhaltsfelder."""
    status_anzeige = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = VorlagenVersion
        fields = [
            'id', 'vorlage', 'version', 'status', 'status_anzeige', 'betreff', 'inhalt',
            'email_begleittext', 'eingabefelder', 'pflicht_platzhalter', 'parameter',
            'freigegeben_am', 'freigegeben_von', 'erstellt_am', 'erstellt_von',
        ]
        read_only_fields = [
            'id', 'vorlage', 'version', 'status', 'freigegeben_am', 'freigegeben_von',
            'erstellt_am', 'erstellt_von',
        ]

    def validate_inhalt(self, wert):
        fehler = blockstruktur_service.pruefe_blockstruktur(wert)
        if fehler:
            raise serializers.ValidationError(fehler)
        return wert

    def validate_eingabefelder(self, wert):
        fehler = eingabefelder_service.pruefe_definition(wert)
        if fehler:
            raise serializers.ValidationError(fehler)
        return wert

    def validate_pflicht_platzhalter(self, wert):
        if not isinstance(wert, list) or not all(isinstance(p, str) for p in wert):
            raise serializers.ValidationError('Pflicht-Platzhalter müssen eine Liste von Namen sein.')
        return wert

    def validate_parameter(self, wert):
        if not isinstance(wert, dict):
            raise serializers.ValidationError('Parameter müssen ein Objekt sein.')
        return wert


class VersionAnlegenSerializer(VorlagenVersionSerializer):
    """Eingabe für ``POST /vorlagen/{id}/versionen/``: Inhaltsfelder + optional ``basis_version``."""
    basis_version = serializers.PrimaryKeyRelatedField(
        queryset=VorlagenVersion.objects.all(), required=False, allow_null=True,
        help_text='Kopiert diese Version (z. B. die freigegebene) als Ausgangspunkt.',
    )

    class Meta(VorlagenVersionSerializer.Meta):
        fields = VorlagenVersionSerializer.Meta.fields + ['basis_version']
        extra_kwargs = {'betreff': {'required': False}}


class VorlageListSerializer(serializers.ModelSerializer):
    anlass_anzeige = serializers.CharField(source='get_anlass_display', read_only=True)
    objekt_bezeichnung = serializers.SerializerMethodField()
    aktive_version_info = serializers.SerializerMethodField()

    class Meta:
        model = Vorlage
        fields = [
            'id', 'code', 'bezeichnung', 'anlass', 'anlass_anzeige', 'objekt',
            'objekt_bezeichnung', 'briefbogen', 'kanal_standard', 'einzeln_bearbeitbar',
            'aktiv', 'aktive_version', 'aktive_version_info', 'erstellt_am', 'geaendert_am',
        ]
        read_only_fields = ['id', 'aktive_version', 'erstellt_am', 'geaendert_am']
        # DRF erkennt bedingte UniqueConstraints nicht (macht ``code`` fälschlich global eindeutig).
        extra_kwargs = {'code': {'validators': []}}
        validators = []  # Eindeutigkeit (auch global, objekt=NULL) prüft ``vorlage_service.lege_vorlage_an``

    def get_objekt_bezeichnung(self, obj):
        return obj.objekt.bezeichnung if obj.objekt_id else None

    def get_aktive_version_info(self, obj):
        v = obj.aktive_version
        return None if v is None else {'id': str(v.pk), 'version': v.version, 'status': v.status}


class VorlageDetailSerializer(VorlageListSerializer):
    versionen = serializers.SerializerMethodField()

    class Meta(VorlageListSerializer.Meta):
        fields = VorlageListSerializer.Meta.fields + ['versionen']

    def get_versionen(self, obj):
        return [
            {
                'id': str(v.pk), 'version': v.version, 'status': v.status,
                'betreff': v.betreff, 'freigegeben_am': v.freigegeben_am,
                'erstellt_am': v.erstellt_am,
            }
            for v in obj.versionen.all()
        ]


class VorlageAendernSerializer(serializers.ModelSerializer):
    """``PATCH /vorlagen/{id}/`` - Code, Anlass und Objekt sind nach dem Anlegen fest."""

    class Meta:
        model = Vorlage
        fields = ['bezeichnung', 'briefbogen', 'kanal_standard', 'einzeln_bearbeitbar', 'aktiv']

    def validate(self, attrs):
        # Spec 9.3: Vorlagen des Anlasses "vorgang_antwort" bleiben einzeln bearbeitbar.
        if self.instance is not None and self.instance.anlass in vorlage_service.IMMER_EINZELN_BEARBEITBAR:
            attrs['einzeln_bearbeitbar'] = True
        return attrs


class TextbausteinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Textbaustein
        fields = ['id', 'code', 'bezeichnung', 'inhalt', 'objekt', 'aktiv']
        read_only_fields = ['id']
        extra_kwargs = {'code': {'validators': []}}
        validators = []  # Eindeutigkeit (auch global, objekt=NULL) prüft ``validate``

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', None))
        objekt = attrs.get('objekt', getattr(self.instance, 'objekt', None))
        doppelt = Textbaustein.objects.filter(code=code, objekt=objekt)
        if self.instance is not None:
            doppelt = doppelt.exclude(pk=self.instance.pk)
        if doppelt.exists():
            raise serializers.ValidationError(
                {'code': 'Dieser Textbaustein existiert bereits (Code je Objekt bzw. global eindeutig).'})
        return attrs


class BriefbogenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Briefbogen
        fields = [
            'id', 'bezeichnung', 'firma_name', 'firma_strasse', 'firma_plz', 'firma_ort',
            'telefon', 'email', 'web', 'sprechzeiten', 'hinweis_infoblock', 'logo', 'fuss_logo',
            'fuss_firma_zeile1', 'fuss_firma_zeile2', 'fuss_firma_zeile3', 'pflichtangaben',
            'pflichtangaben_anzeigen', 'steuerzeichen_unsichtbar', 'ist_standard', 'aktiv',
        ]
        read_only_fields = ['id']


class VorschauSerializer(serializers.Serializer):
    """Eingabe für ``POST /versionen/{id}/vorschau/``."""
    person_id = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all())
    einheit_id = serializers.PrimaryKeyRelatedField(
        queryset=Einheit.objects.select_related('objekt'), required=False, allow_null=True)
    eingabewerte = serializers.DictField(required=False)


class VorlagenAssistentSerializer(serializers.Serializer):
    """Eingabe für ``POST /vorlagen-assistent/``.

    ``eingabefelder`` (optional) sind die im Editor definierten Felder der Version (nur
    Name/Label/Typ, keine Werte); sie machen ``eingabe.*`` für die KI bekannt.
    """
    anlass = serializers.ChoiceField(choices=list(registry.ANLAESSE))
    stichworte = serializers.CharField(max_length=2000)
    block = serializers.DictField(required=False, allow_null=True)
    eingabefelder = serializers.ListField(child=serializers.DictField(), required=False)

    def validate_stichworte(self, wert):
        if not wert.strip():
            raise serializers.ValidationError('Bitte Stichworte bzw. eine Anweisung angeben.')
        return wert.strip()

    def validate_eingabefelder(self, wert):
        fehler = eingabefelder_service.pruefe_definition(wert)
        if fehler:
            raise serializers.ValidationError(fehler)
        return wert
