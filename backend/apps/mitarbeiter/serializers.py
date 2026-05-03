from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from .models import Mitarbeiter, MitarbeiterObjektZuordnung, ABTEILUNG_CHOICES

User = get_user_model()

VALID_ABTEILUNGEN = {c[0] for c in ABTEILUNG_CHOICES}


class MitarbeiterListSerializer(serializers.ModelSerializer):
    vorname  = serializers.CharField(source='user.first_name', read_only=True)
    nachname = serializers.CharField(source='user.last_name',  read_only=True)
    vollname = serializers.SerializerMethodField()
    email    = serializers.EmailField(source='user.email',    read_only=True)
    username = serializers.CharField(source='user.username',  read_only=True)

    def get_vollname(self, obj):
        return obj.user.get_full_name()

    class Meta:
        model  = Mitarbeiter
        fields = [
            'id', 'vorname', 'nachname', 'vollname', 'email', 'username',
            'abteilungen', 'telefon', 'aktiv', 'eingetreten_am', 'erstellt_am',
        ]


class MitarbeiterSerializer(serializers.ModelSerializer):
    vorname  = serializers.CharField(source='user.first_name', required=True)
    nachname = serializers.CharField(source='user.last_name',  required=True)
    email    = serializers.EmailField(source='user.email',     required=True)
    username = serializers.SerializerMethodField()
    vollname = serializers.SerializerMethodField()
    passwort = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8,
    )
    abteilungen = serializers.ListField(
        child=serializers.ChoiceField(choices=[c[0] for c in ABTEILUNG_CHOICES]),
        min_length=1,
    )

    def get_username(self, obj):
        return obj.user.username

    def get_vollname(self, obj):
        return obj.user.get_full_name()

    class Meta:
        model  = Mitarbeiter
        fields = [
            'id', 'vorname', 'nachname', 'vollname', 'email', 'username', 'passwort',
            'abteilungen', 'telefon', 'aktiv', 'eingetreten_am', 'erstellt_am',
        ]
        read_only_fields = ['id', 'erstellt_am']

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(username=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise serializers.ValidationError(
                'Diese E-Mail-Adresse wird bereits als Benutzername verwendet.'
            )
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get('passwort'):
            raise serializers.ValidationError({'passwort': 'Passwort ist beim Anlegen Pflicht.'})
        return attrs

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        vorname  = user_data.get('first_name', '').strip()
        nachname = user_data.get('last_name',  '').strip()
        email    = user_data.get('email',      '').strip().lower()
        passwort = validated_data.pop('passwort', '')

        user = User.objects.create_user(
            username   = email,
            password   = passwort,
            email      = email,
            first_name = vorname,
            last_name  = nachname,
        )
        return Mitarbeiter.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        passwort  = validated_data.pop('passwort', None)

        user = instance.user
        if 'first_name' in user_data:
            user.first_name = user_data['first_name'].strip()
        if 'last_name' in user_data:
            user.last_name = user_data['last_name'].strip()
        if 'email' in user_data:
            new_email = user_data['email'].strip().lower()
            user.email    = new_email
            user.username = new_email
        if passwort:
            user.set_password(passwort)
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ZuordnungListSerializer(serializers.ModelSerializer):
    mitarbeiter_id = serializers.IntegerField(source='mitarbeiter.id', read_only=True)
    vollname       = serializers.SerializerMethodField()
    email          = serializers.CharField(source='mitarbeiter.user.email', read_only=True)
    abteilungen    = serializers.ListField(source='mitarbeiter.abteilungen', read_only=True)

    def get_vollname(self, obj):
        return obj.mitarbeiter.user.get_full_name()

    class Meta:
        model  = MitarbeiterObjektZuordnung
        fields = ['id', 'mitarbeiter_id', 'vollname', 'email', 'abteilungen', 'aufgabe']


class ZuordnungCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model      = MitarbeiterObjektZuordnung
        fields     = ['id', 'mitarbeiter', 'objekt', 'aufgabe']
        validators = [
            UniqueTogetherValidator(
                queryset=MitarbeiterObjektZuordnung.objects.all(),
                fields=['mitarbeiter', 'objekt'],
                message='Dieser Mitarbeiter ist dem Objekt bereits zugeordnet.',
            )
        ]

    def validate(self, attrs):
        mitarbeiter = attrs.get('mitarbeiter') or (self.instance.mitarbeiter if self.instance else None)
        aufgabe = attrs.get('aufgabe', '')
        if mitarbeiter and aufgabe and aufgabe not in mitarbeiter.abteilungen:
            raise serializers.ValidationError(
                {'aufgabe': 'Diese Aufgabe ist für diesen Mitarbeiter nicht verfügbar.'}
            )
        return attrs


class ZuordnungPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MitarbeiterObjektZuordnung
        fields = ['id', 'aufgabe']

    def validate_aufgabe(self, value):
        mitarbeiter = self.instance.mitarbeiter
        if value and value not in mitarbeiter.abteilungen:
            raise serializers.ValidationError(
                'Diese Aufgabe ist für diesen Mitarbeiter nicht verfügbar.'
            )
        return value
