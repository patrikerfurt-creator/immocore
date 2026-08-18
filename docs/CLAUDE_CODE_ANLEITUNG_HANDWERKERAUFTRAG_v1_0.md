# Claude Code – Anleitung: Handwerkerauftrag-Management (IMMOCORE)

**Version:** 1.0  
**Status:** Implementierungsreif  
**Datum:** August 2026

---

## Ziel

Aus einem **Vorgang** kann ein Handwerker beauftragt werden. Der Handwerker erhält per E-Mail einen eindeutigen Auftrag mit zwei Token-basierten Links (Annehmen/Ablehnen) ohne Login-Hürde. Das System führt eine zentrale **Auftrags-Übersicht** mit Statusverfolgung, Filterung und historischen Daten.

**Folgende Bestanteile werden implementiert:**
1. Erweiterung des `Kreditor`-Modells um Gewerk-Kategorisierung
2. Many-to-Many Beziehung zwischen `WEGObjekt` und `Kreditor` (mit optionaler Reihenfolge)
3. `Handwerkerauftrag`-Modell (Hauptentität)
4. Token-basierte E-Mail-Authentifizierung (Accept/Reject ohne Login)
5. Neue Admin-UI zur Handwerker-Zuweisung pro Objekt
6. Button „Handwerker beauftragen" im Vorgang-Detail
7. Auftrags-Dashboard mit Filterung & Statusverfolgung

---

## Kontext & Annahmen

- `Kreditor`-Modell existiert bereits (name, kontakt, email, adresse, etc.)
- `WEGObjekt` ist vorhanden (Liegenschaft/Gebäude)
- `Vorgang`-Modell existiert (neue Spalte `handwerkerauftrag` optional)
- `Dokument`-Modell existiert (aus DMS-Modul)
- `Mail-Intake`-Pipeline existiert (aus Mail-Intake-Modul)
- Celery + Redis für E-Mail-Versand vorhanden
- Django 5, React 18 Standard

**Dependencies:**
- `python-holidays` für Businessdays-Berechnung: `pip install python-holidays`

**Keine Automatisierung** in Phase 1.0 – alle Aufträge werden manuell aus der Vorgang-UI getriggert.

---

## Datenmodell

### 1. `Gewerk` – Master-Tabelle (optional separate Modell)

**Entscheidung:** Aus Einfachheit wird `gewerk` als `CharField` mit Choices auf dem `Kreditor` implementiert. Falls später differenzierte Gewerk-Stammdaten nötig sind (Gebühren, Spezialisierung, Zuordnungen), kann in Phase 2 zu separatem Modell migriert werden.

```python
# models/kreditor.py

GEWERK_CHOICES = [
    ('sanitaer', 'Sanitär'),
    ('elektrik', 'Elektrik'),
    ('dachdeckerei', 'Dachdeckerei'),
    ('mauerwerk', 'Mauerwerk'),
    ('tischlerei', 'Tischlerei'),
    ('tapezierung', 'Tapezierung'),
    ('sonstige', 'Sonstige'),
]

class Kreditor(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    kontakt_person = models.CharField(max_length=200, blank=True)
    telefon = models.CharField(max_length=20, blank=True)
    adresse = models.TextField(blank=True)
    
    # NEU:
    gewerk = models.CharField(
        max_length=50,
        choices=GEWERK_CHOICES,
        default='sonstige',
        help_text="Gewerkszuordnung (z.B. Sanitär, Elektrik)"
    )
    
    ist_handwerker = models.BooleanField(
        default=False,
        help_text="Ist dieser Kreditor ein Handwerker (kann Aufträge erhalten)?"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 2. `WEGObjektHandwerker` – Many-to-Many mit Ordnung

```python
# models/objekt.py

class WEGObjekt(models.Model):
    name = models.CharField(max_length=255)
    adresse = models.TextField()
    # ... bestehende Felder ...
    
    # NEU: Handwerker-Zuordnung
    handwerker = models.ManyToManyField(
        'Kreditor',
        through='WEGObjektHandwerker',
        related_name='objekte',
        limit_choices_to={'ist_handwerker': True},
        blank=True
    )

class WEGObjektHandwerker(models.Model):
    """
    Zwischentabelle: Ordnet Handwerker einem Objekt zu.
    Erlaubt mehrere Handwerker pro Objekt mit optionaler Priorität/Ordnung.
    """
    objekt = models.ForeignKey(WEGObjekt, on_delete=models.CASCADE)
    kreditor = models.ForeignKey(Kreditor, on_delete=models.CASCADE)
    
    # Optional: Prioritätsordnung (1=erste Wahl, 2=zweite Wahl, etc.)
    prioritaet = models.PositiveIntegerField(
        default=1,
        help_text="Auswahlreihenfolge (1=erste Wahl)"
    )
    
    # Zusätzliche Kontaktinformation für diesen Handwerker im Kontext dieses Objekts
    notiz = models.TextField(blank=True, help_text="Besonderheiten/Zugang/etc.")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('objekt', 'kreditor')
        ordering = ['prioritaet', 'kreditor__name']
```

### 3. `Handwerkerauftrag` – Hauptentität

```python
# models/auftrag.py

from django.db import models
from django.utils.crypto import get_random_string

AUFTRAG_STATUS = [
    ('entwurf', 'Entwurf'),                      # Intern erstellt, noch nicht versendet
    ('versendet', 'Versendet'),                  # E-Mail rausgegangen, wartet auf Antwort
    ('angenommen', 'Angenommen'),                # Handwerker akzeptiert
    ('abgelehnt', 'Abgelehnt'),                  # Handwerker lehnt ab
    ('in_arbeit', 'In Arbeit'),                  # Optisch: manuell markiert als laufend
    ('abgeschlossen', 'Abgeschlossen'),          # Arbeit fertig
    ('storniert', 'Storniert'),                  # Admin storniert
]

class Handwerkerauftrag(models.Model):
    # Beziehungen
    vorgang = models.ForeignKey(
        'Vorgang',
        on_delete=models.CASCADE,
        related_name='handwerkerauftraege',
        null=True,
        blank=True,
        help_text="Ursprünglicher Vorgang (optional, für Kontext)"
    )
    objekt = models.ForeignKey(
        'WEGObjekt',
        on_delete=models.CASCADE,
        related_name='handwerkerauftraege'
    )
    kreditor = models.ForeignKey(
        'Kreditor',
        on_delete=models.CASCADE,
        limit_choices_to={'ist_handwerker': True}
    )
    erstellt_von = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='erstellte_auftraege'
    )
    
    # Inhalte
    titel = models.CharField(
        max_length=255,
        help_text="Kurztitel des Auftrags (z.B. 'Rohwasserleitung reparieren')"
    )
    beschreibung = models.TextField(
        blank=True,
        help_text="Detaillierte Beschreibung der Arbeiten"
    )
    
    # Scheduling & Priorität
    gewuenscht_ab = models.DateField(
        null=True,
        blank=True,
        help_text="Gewünschtes Startdatum"
    )
    prioritaet = models.CharField(
        max_length=20,
        choices=[('low', 'Niedrig'), ('normal', 'Normal'), ('hoch', 'Hoch')],
        default='normal'
    )
    
    # Kostenschätzung (optional)
    geschaetzte_kosten = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="EUR (ungefähre Schätzung)"
    )
    
    # Status & Workflow
    status = models.CharField(
        max_length=20,
        choices=AUFTRAG_STATUS,
        default='entwurf'
    )
    
    # Annahme/Ablehnung durch Handwerker
    angenommen_am = models.DateTimeField(null=True, blank=True)
    abgelehnt_am = models.DateTimeField(null=True, blank=True)
    ablehnung_grund = models.TextField(blank=True, help_text="Grund bei Ablehnung")
    
    # Abschluss & Rechnungsverkettung
    abgeschlossen_am = models.DateTimeField(null=True, blank=True)
    abschluss_notiz = models.TextField(blank=True, help_text="Was wurde getan?")
    
    # Rechnung (verlinkt via Mail-Intake)
    rechnung_dokument = models.OneToOneField(
        'Dokument',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handwerkerauftrag',
        help_text="Handwerker-Rechnung (eingescannt via Mail-Intake)"
    )
    rechnung_eingegangen_am = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Wann wurde die Rechnung eingescannt?"
    )
    
    # GoBD-Konformität
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['objekt', 'status']),
            models.Index(fields=['kreditor', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"#{self.id} – {self.titel} ({self.get_status_display()})"
```

### 4. `AuftragsbestätigungsToken` – Magische Links

```python
# models/auftrag.py

import secrets

class AuftragsbestätigungsToken(models.Model):
    """
    Token für Accept/Reject-Links.
    Ermöglicht Handwerker-Authentifizierung ohne Login.
    """
    auftrag = models.OneToOneField(
        Handwerkerauftrag,
        on_delete=models.CASCADE,
        related_name='token'
    )
    
    # UUID-ähnlicher Secret für URLs
    accept_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True
    )
    reject_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True
    )
    
    # Gültigkeitsdauer
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateTimeField()
    abgelaufen = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if not self.accept_token:
            self.accept_token = secrets.token_urlsafe(48)
        if not self.reject_token:
            self.reject_token = secrets.token_urlsafe(48)
        if not self.gueltig_bis:
            # Token-Gültigkeit basierend auf Auftrag-Priorität
            # + Businessdays-Berechnung (keine Sa/So/Feiertag)
            self.gueltig_bis = berechne_gueltig_bis(self.auftrag.prioritaet)
        super().save(*args, **kwargs)


def berechne_gueltig_bis(prioritaet):
    """
    Berechnet Gültigkeitsdatum unter Berücksichtigung von Businessdays.
    - Dringend: 3 Businessdays
    - Normal: 7 Businessdays
    - Niedrig: 14 Businessdays
    
    Businessdays = keine Samstag, Sonntag, Feiertage (DE)
    """
    from datetime import timedelta
    from django.utils import timezone
    import holidays
    
    # Tage-Mapping
    tage_map = {
        'hoch': 3,
        'normal': 7,
        'low': 14,
    }
    tage_noetig = tage_map.get(prioritaet, 7)
    
    # Feiertage (Deutschland)
    de_holidays = holidays.Germany(years=2026)
    
    # Businessdays zählen
    current = timezone.now().date()
    businessdays_gezaehlt = 0
    
    while businessdays_gezaehlt < tage_noetig:
        current += timedelta(days=1)
        # Überspringe Wochenend & Feiertage
        if current.weekday() < 5 and current not in de_holidays:
            businessdays_gezaehlt += 1
    
    # Zurück zu DateTime (Enddatum 23:59:59)
    return timezone.make_aware(
        timezone.datetime.combine(current, timezone.datetime.max.time())
    )
    
    def ist_gueltig(self):
        return not self.abgelaufen and timezone.now() < self.gueltig_bis
```

---

## Phasen

### Phase A: Datenbank-Migrationen

**HALT-Gate:** Alle Migrationen sind **additive**. Keine bestehenden Spalten werden gelöscht oder geändert.

**Migrationen:**
1. `Kreditor` erweitern: `gewerk` + `ist_handwerker` hinzufügen
2. `WEGObjekt` erweitern: M2M `handwerker` hinzufügen (erzeugt Zwischentabelle)
3. `Handwerkerauftrag` neu erstellen
4. `AuftragsbestätigungsToken` neu erstellen

```bash
python manage.py makemigrations
python manage.py migrate
```

**Smoke-Test Kriterium:**
- Migrations without errors
- `python manage.py check` passes
- All models can be instantiated in Django shell

---

### Phase B: Admin-Interface (Handwerker-Zuordnung)

**Ziel:** Admin kann pro `WEGObjekt` beliebig viele Handwerker zuordnen.

**UI-Änderungen:**

1. **Kreditor Admin erweitern:**
   - Fieldset: `gewerk` + `ist_handwerker` checkbox
   - `list_filter` nach Gewerk & ist_handwerker
   - `search_fields` nach Name, Kontakt

2. **WEGObjekt Admin erweitern:**
   - Inline-Admin für `WEGObjektHandwerker`
   - Sortierbare Liste (Prioritätsordnung)
   - Spalten: Handwerker-Name, Gewerk, Priorität, Notiz

```python
# admin.py

class WEGObjektHandwerkerInline(admin.TabularInline):
    model = WEGObjektHandwerker
    extra = 1
    fields = ['kreditor', 'prioritaet', 'notiz']
    ordering = ['prioritaet']
    raw_id_fields = ['kreditor']

class WEGObjektAdmin(admin.ModelAdmin):
    inlines = [WEGObjektHandwerkerInline, ...]
    # ...
```

**Smoke-Test Kriterium:**
- Admin-Pages laden ohne Fehler
- Handwerker können pro Objekt zugeordnet werden
- Prioritätsordnung ist veränderbar

---

### Phase C: API – Auftrag erstellen & E-Mail-Versand

**Endpoint:** `POST /api/vorgang/{vorgang_id}/handwerkerauftrag/`

**Request-Body:**
```json
{
  "kreditor_id": 42,
  "titel": "Rohwasserleitung reparieren",
  "beschreibung": "Lecktage im Keller, Wasser läuft aus...",
  "gewuenscht_ab": "2026-08-25",
  "prioritaet": "hoch",
  "geschaetzte_kosten": "450.00"
}
```

**Response (201 Created):**
```json
{
  "id": 123,
  "status": "versendet",
  "titel": "Rohwasserleitung reparieren",
  "kreditor": { "id": 42, "name": "Müller Sanitär GmbH", "email": "kontakt@mueller-sanitaer.de" },
  "objekt": { "id": 7, "name": "Objekt Beispielstraße 42" },
  "created_at": "2026-08-17T10:30:00Z",
  "email_sent_at": "2026-08-17T10:30:15Z"
}
```

**Backend-Logik:**

```python
# services/auftrag_service.py

from django.utils import timezone
from datetime import timedelta
from celery import shared_task

class AuftragsService:
    
    @staticmethod
    def erstelle_auftrag(vorgang, kreditor, titel, beschreibung, 
                         gewuenscht_ab=None, prioritaet='normal', 
                         geschaetzte_kosten=None, erstellt_von=None):
        """
        1. Auftrag anlegen
        2. Token generieren
        3. E-Mail versenden
        """
        
        auftrag = Handwerkerauftrag.objects.create(
            vorgang=vorgang,
            objekt=vorgang.objekt,
            kreditor=kreditor,
            titel=titel,
            beschreibung=beschreibung,
            gewuenscht_ab=gewuenscht_ab,
            prioritaet=prioritaet,
            geschaetzte_kosten=geschaetzte_kosten,
            erstellt_von=erstellt_von,
            status='entwurf'
        )
        
        # Token erstellen
        token = AuftragsbestätigungsToken.objects.create(
            auftrag=auftrag
        )
        
        # E-Mail versendet?
        versand_ok = versende_auftragsmail(auftrag, token)
        
        if versand_ok:
            auftrag.status = 'versendet'
            auftrag.save(update_fields=['status'])
        
        return auftrag


@shared_task
def versende_auftragsmail(auftrag_id):
    """Celery Task für E-Mail-Versand"""
    auftrag = Handwerkerauftrag.objects.get(id=auftrag_id)
    token = auftrag.token
    
    # URLs
    accept_url = f"https://immocore.example.com/api/auftrag/{auftrag.id}/akzeptieren/{token.accept_token}/"
    reject_url = f"https://immocore.example.com/api/auftrag/{auftrag.id}/ablehnen/{token.reject_token}/"
    
    # HTML-Template rendern
    html_body = render_to_string('email/handwerkerauftrag.html', {
        'auftrag': auftrag,
        'accept_url': accept_url,
        'reject_url': reject_url,
        'token': token,
    })
    
    # Versenden
    from django.core.mail import send_mail
    try:
        send_mail(
            subject=f"Neuer Auftrag: {auftrag.titel}",
            message="Siehe HTML-Nachricht",
            from_email="info@demme-immobilien.de",
            recipient_list=[auftrag.kreditor.email],
            html_message=html_body,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"E-Mail-Versand fehlgeschlagen: {e}")
        return False
```

**E-Mail-Template (`templates/email/handwerkerauftrag.html`):**

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    
    <h2>Neuer Auftrag für {{ auftrag.kreditor.name }}</h2>
    
    <p><strong>Objekt:</strong> {{ auftrag.objekt.name }}</p>
    <p><strong>Adresse:</strong> {{ auftrag.objekt.adresse }}</p>
    
    <hr>
    
    <h3>{{ auftrag.titel }}</h3>
    <p>{{ auftrag.beschreibung }}</p>
    
    <p>
        <strong>Priorität:</strong> {{ auftrag.get_prioritaet_display }}<br>
        {% if auftrag.gewuenscht_ab %}
            <strong>Gewünscht ab:</strong> {{ auftrag.gewuenscht_ab }}<br>
        {% endif %}
        {% if auftrag.geschaetzte_kosten %}
            <strong>Geschätzte Kosten:</strong> {{ auftrag.geschaetzte_kosten }} EUR<br>
        {% endif %}
    </p>
    
    <hr>
    
    <h3>Auftrag annehmen oder ablehnen?</h3>
    
    <p>
        <a href="{{ accept_url }}" 
           style="display: inline-block; padding: 12px 24px; background-color: #28a745; 
                  color: white; text-decoration: none; border-radius: 4px; font-weight: bold;">
            ✓ Auftrag Annehmen
        </a>
        &nbsp;
        <a href="{{ reject_url }}" 
           style="display: inline-block; padding: 12px 24px; background-color: #dc3545; 
                  color: white; text-decoration: none; border-radius: 4px; font-weight: bold;">
            ✗ Auftrag Ablehnen
        </a>
    </p>
    
    <p style="font-size: 0.9em; color: #666;">
        Links gültig bis: {{ token.gueltig_bis|date:"d.m.Y H:i" }} Uhr<br>
        ({{ auftrag.get_prioritaet_display }} Priorität = {{ token.tage_gueltig }} Geschäftstage)<br>
        Auftrag-ID: {{ auftrag.id }}<br>
        <strong>Tipp:</strong> Wenn Sie die Arbeiten abgeschlossen haben, senden Sie die Rechnung 
        per E-Mail an <a href="mailto:rechnungen@demme-immo.de">rechnungen@demme-immo.de</a> 
        mit der Auftrag-ID im Betreff (z.B. "Auftrag #{{ auftrag.id }}")
    </p>

</body>
</html>
```

**Smoke-Test Kriterium:**
- API-Endpoint akzeptiert gültige Requests
- Auftrag wird angelegt mit Status `entwurf` → `versendet`
- Token wird generiert
- E-Mail wird versendet (oder in Celery-Queue für async Task)

---

### Phase D: Public Endpoints – Accept/Reject ohne Auth

**Ziel:** Handwerker können per Token-Link Auftrag akzeptieren/ablehnen, *ohne* eingeloggt zu sein.

**Endpoints:**

1. `GET /api/auftrag/{auftrag_id}/akzeptieren/{accept_token}/`
   - Status auf `angenommen` setzen
   - `angenommen_am = now()`
   - Weiterleitung zu Bestätigungs-Seite
   - Admin-E-Mail: "Auftrag angenommen von [Handwerker]"

2. `GET /api/auftrag/{auftrag_id}/ablehnen/{reject_token}/`
   - Optionales Formular für Ablehnung-Grund
   - Status auf `abgelehnt` setzen
   - `abgelehnt_am = now()`
   - `ablehnung_grund` speichern
   - Admin-E-Mail: "Auftrag abgelehnt: [Grund]"

```python
# views/auftrag.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def akzeptiere_auftrag(request, auftrag_id, accept_token):
    """
    Handwerker akzeptiert Auftrag via magischer Link.
    """
    auftrag = get_object_or_404(Handwerkerauftrag, id=auftrag_id)
    token = get_object_or_404(AuftragsbestätigungsToken, auftrag=auftrag)
    
    # Token-Validierung
    if not token.ist_gueltig():
        return Response({'error': 'Token abgelaufen'}, status=400)
    
    if token.accept_token != accept_token:
        return Response({'error': 'Ungültiger Token'}, status=403)
    
    # Status ändern
    auftrag.status = 'angenommen'
    auftrag.angenommen_am = timezone.now()
    auftrag.save(update_fields=['status', 'angenommen_am'])
    
    # Admin benachrichtigen
    admin_emails = list(User.objects.filter(is_staff=True).values_list('email', flat=True))
    send_mail(
        subject=f"Auftrag #{auftrag.id} angenommen",
        message=f"Handwerker {auftrag.kreditor.name} hat Auftrag '{auftrag.titel}' akzeptiert.",
        from_email="info@demme-immobilien.de",
        recipient_list=admin_emails,
    )
    
    return Response({
        'status': 'success',
        'auftrag_id': auftrag.id,
        'title': 'Auftrag angenommen',
        'message': f'Vielen Dank! Ihr Auftrag wurde übermittelt.'
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def lehne_auftrag_ab(request, auftrag_id, reject_token):
    """
    Handwerker lehnt Auftrag via magischer Link ab.
    """
    auftrag = get_object_or_404(Handwerkerauftrag, id=auftrag_id)
    token = get_object_or_404(AuftragsbestätigungsToken, auftrag=auftrag)
    
    # Token-Validierung
    if not token.ist_gueltig():
        return Response({'error': 'Token abgelaufen'}, status=400)
    
    if token.reject_token != reject_token:
        return Response({'error': 'Ungültiger Token'}, status=403)
    
    # Bei POST: Grund erfassen
    grund = ""
    if request.method == 'POST':
        grund = request.data.get('grund', '')
    
    # Status ändern
    auftrag.status = 'abgelehnt'
    auftrag.abgelehnt_am = timezone.now()
    auftrag.ablehnung_grund = grund
    auftrag.save(update_fields=['status', 'abgelehnt_am', 'ablehnung_grund'])
    
    # Admin benachrichtigen
    admin_emails = list(User.objects.filter(is_staff=True).values_list('email', flat=True))
    send_mail(
        subject=f"Auftrag #{auftrag.id} abgelehnt",
        message=f"Handwerker {auftrag.kreditor.name} hat Auftrag '{auftrag.titel}' abgelehnt.\n\n"
                f"Grund: {grund}",
        from_email="info@demme-immobilien.de",
        recipient_list=admin_emails,
    )
    
    return Response({
        'status': 'success',
        'auftrag_id': auftrag.id,
        'title': 'Auftrag abgelehnt',
        'message': f'Vielen Dank für die Rückmeldung.'
    })
```

**Frontend – React: Bestätigungs-Seite**

```jsx
// pages/AuftragBestaetigung.jsx

import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

export default function AuftragBestaetigung() {
    const { auftrag_id, token } = useParams();
    const [status, setStatus] = useState('loading');
    const [message, setMessage] = useState('');
    
    useEffect(() => {
        const action = window.location.pathname.includes('/akzeptieren/') ? 'akzeptieren' : 'ablehnen';
        
        fetch(`/api/auftrag/${auftrag_id}/${action}/${token}/`)
            .then(r => r.json())
            .then(data => {
                setStatus(data.status);
                setMessage(data.message);
            })
            .catch(err => {
                setStatus('error');
                setMessage('Fehler beim Verarbeiten.');
            });
    }, [auftrag_id, token]);
    
    return (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
            {status === 'loading' && <p>Verarbeite...</p>}
            {status === 'success' && (
                <>
                    <h2 style={{ color: '#28a745' }}>✓ Erfolgreich</h2>
                    <p>{message}</p>
                </>
            )}
            {status === 'error' && (
                <>
                    <h2 style={{ color: '#dc3545' }}>✗ Fehler</h2>
                    <p>{message}</p>
                </>
            )}
        </div>
    );
}
```

**Smoke-Test Kriterium:**
- Accept/Reject Endpoints akzeptieren gültige Tokens
- Status wird korrekt aktualisiert
- Admin-E-Mails werden versendet
- Bestätigungs-Seite zeigt Erfolg/Fehler korrekt

---

### Phase E: Rechnungsverkettung via Mail-Intake

**Ziel:** Handwerker mailt Rechnung → System erkennt Auftrag-ID → auto-link zur `Handwerkerauftrag`.

**Workflow:**
1. Handwerker sendet Rechnung per E-Mail an `rechnungen@demme-immo.de`
2. Mail-Intake-Pipeline verarbeitet die E-Mail (existierendes System)
3. In Betreff/Body oder Dateiname wird Auftrag-ID gesucht (z.B. "Auftrag #123" oder "HWA-123")
4. Wenn erkannt: `Handwerkerauftrag.rechnung_dokument` wird gespeichert
5. Status wird optional auf `abgeschlossen` aktualisiert (falls fertig)

**Integration in Mail-Intake-Classifier:**

```python
# services/mail_intake.py (Erweiterung der bestehenden Pipeline)

def erkenne_handwerkerauftrag_id(email_betreff, email_body, anhang_filenames):
    """
    Sucht nach Handwerkerauftrag-ID im Betreff/Body/Dateiname.
    Regex-Patterns: 
    - "Auftrag #123"
    - "Auftrag 123"
    - "HWA-123"
    - Dateiname: "auftrag_123_rechnung.pdf"
    """
    import re
    
    # Kombiniere Betreff + Body + Dateiname
    text = f"{email_betreff} {email_body} {' '.join(anhang_filenames)}"
    
    # Regex: Suche nach Auftrag-ID
    patterns = [
        r'(?:Auftrag|HWA)[\s\-]*#?(\d+)',
        r'auftrag[\s_](\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                auftrag_id = int(match.group(1))
                # Verifiziere, dass Auftrag existiert
                if Handwerkerauftrag.objects.filter(id=auftrag_id).exists():
                    return auftrag_id
            except:
                pass
    
    return None


def verarbeite_handwerkerauftrag_rechnung(email_obj, erkannte_rechnung_id=None):
    """
    Wenn Auftrag erkannt → Rechnung verlinken.
    Wird aufgerufen von der Mail-Intake-Pipeline nach RechnungsErkennungsLog-Erstellung.
    """
    auftrag_id = erkenne_handwerkerauftrag_id(
        email_obj.subject,
        email_obj.body,
        [a.filename for a in email_obj.anhang.all()]
    )
    
    if not auftrag_id:
        return None
    
    try:
        auftrag = Handwerkerauftrag.objects.get(id=auftrag_id)
    except Handwerkerauftrag.DoesNotExist:
        return None
    
    # Finde das gerade erstellte Dokument (via erkannte_rechnung_id / RechnungsErkennungsLog)
    if erkannte_rechnung_id:
        try:
            log = RechnungsErkennungsLog.objects.get(id=erkannte_rechnung_id)
            dokument = log.dokument  # Existiert nach Phase C des Mail-Intake
            
            # Verlinke
            auftrag.rechnung_dokument = dokument
            auftrag.rechnung_eingegangen_am = timezone.now()
            
            # Optional: Auto-complete, wenn Auftrag in Bearbeitung
            if auftrag.status == 'in_arbeit':
                auftrag.status = 'abgeschlossen'
                auftrag.abgeschlossen_am = timezone.now()
            
            auftrag.save(update_fields=['rechnung_dokument', 'rechnung_eingegangen_am', 'status', 'abgeschlossen_am'])
            
            # Log für Audit
            print(f"Handwerkerauftrag #{auftrag_id} mit Rechnung verlinkt")
            return auftrag
        except RechnungsErkennungsLog.DoesNotExist:
            pass
    
    return None
```

**Integration in Bestandscode:**

Die `Mail-Intake`-Pipeline (bestehend aus `versende_auftragsmail` → `klassifiziere_rechnung` → `erstelle_rechnungserkennungslog`) wird um einen neuen Service-Call erweitert:

```python
# Im bestehenden Mail-Intake-Workflow nach Dokument-Erstellung:

# ... (existierende Mail-Intake-Logik)
log = RechnungsErkennungsLog.objects.create(...)  # Phase C

# NEU: Prüfe auf Handwerkerauftrag-Verkettung
verarbeite_handwerkerauftrag_rechnung(
    email_obj=email_message,
    erkannte_rechnung_id=log.id
)
```

**Smoke-Test Kriterium:**
- Handwerker sendet E-Mail mit Rechnung + Auftrag-ID im Betreff
- System erkennt Auftrag-ID
- `Handwerkerauftrag.rechnung_dokument` wird gespeichert
- Auftrag-Detail zeigt verlinkte Rechnung
- Status wird auf `abgeschlossen` aktualisiert (optional)

---

### Phase F: Auftrags-Dashboard & Filtration

**Ziel:** Zentrale Übersicht aller Aufträge mit Such- & Filterfunktion.

**Endpoint:** `GET /api/handwerkerauftraege/`

**Query-Parameter:**
- `status=versendet,angenommen,abgelehnt,in_arbeit,abgeschlossen`
- `objekt_id=7`
- `kreditor_id=42`
- `prioritaet=hoch`
- `search=Rohwasser` (durchsucht titel + beschreibung)
- `ordering=-created_at` (oder `angenommen_am`, `abgelehnt_am`)

**Response:**
```json
{
  "count": 42,
  "results": [
    {
      "id": 123,
      "titel": "Rohwasserleitung reparieren",
      "status": "angenommen",
      "objekt": { "id": 7, "name": "Objekt Beispielstraße 42" },
      "kreditor": { "id": 42, "name": "Müller Sanitär GmbH", "gewerk": "sanitaer" },
      "prioritaet": "hoch",
      "geschaetzte_kosten": "450.00",
      "created_at": "2026-08-17T10:30:00Z",
      "angenommen_am": "2026-08-17T14:20:00Z",
      "abgelehnt_am": null
    },
    // ...
  ]
}
```

**React Frontend – Dashboard-Komponente:**

```jsx
// pages/HandwerkeraufträgeDashboard.jsx

import { useState, useEffect } from 'react';

const STATUS_FARBEN = {
    entwurf: '#999',
    versendet: '#007bff',
    angenommen: '#28a745',
    abgelehnt: '#dc3545',
    in_arbeit: '#ff9800',
    abgeschlossen: '#17a2b8',
    storniert: '#666',
};

export default function HandwerkeraufträgeDashboard() {
    const [auftraege, setAuftraege] = useState([]);
    const [filter, setFilter] = useState({
        status: '',
        objekt_id: '',
        kreditor_id: '',
        prioritaet: '',
        search: '',
    });
    const [loading, setLoading] = useState(false);
    
    useEffect(() => {
        const query = new URLSearchParams(filter).toString();
        setLoading(true);
        fetch(`/api/handwerkerauftraege/?${query}`)
            .then(r => r.json())
            .then(data => {
                setAuftraege(data.results || []);
                setLoading(false);
            });
    }, [filter]);
    
    return (
        <div style={{ padding: '1rem' }}>
            <h1>Handwerkeraufträge</h1>
            
            {/* Filter */}
            <div style={{ marginBottom: '1rem', padding: '1rem', backgroundColor: '#f5f5f5' }}>
                <input
                    type="text"
                    placeholder="Suche..."
                    value={filter.search}
                    onChange={(e) => setFilter({...filter, search: e.target.value})}
                    style={{ width: '100%', padding: '0.5rem', marginBottom: '0.5rem' }}
                />
                
                <select
                    value={filter.status}
                    onChange={(e) => setFilter({...filter, status: e.target.value})}
                    style={{ marginRight: '1rem', padding: '0.5rem' }}
                >
                    <option value="">Alle Status</option>
                    <option value="versendet">Versendet</option>
                    <option value="angenommen">Angenommen</option>
                    <option value="abgelehnt">Abgelehnt</option>
                    <option value="in_arbeit">In Arbeit</option>
                    <option value="abgeschlossen">Abgeschlossen</option>
                </select>
                
                <select
                    value={filter.prioritaet}
                    onChange={(e) => setFilter({...filter, prioritaet: e.target.value})}
                    style={{ padding: '0.5rem' }}
                >
                    <option value="">Alle Prioritäten</option>
                    <option value="low">Niedrig</option>
                    <option value="normal">Normal</option>
                    <option value="hoch">Hoch</option>
                </select>
            </div>
            
            {/* Tabelle */}
            {loading ? (
                <p>Lädt...</p>
            ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ backgroundColor: '#f9f9f9', borderBottom: '2px solid #ddd' }}>
                            <th style={{ padding: '0.75rem', textAlign: 'left' }}>ID</th>
                            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Titel</th>
                            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Objekt</th>
                            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Handwerker</th>
                            <th style={{ padding: '0.75rem', textAlign: 'center' }}>Status</th>
                            <th style={{ padding: '0.75rem', textAlign: 'right' }}>Kosten</th>
                            <th style={{ padding: '0.75rem', textAlign: 'left' }}>Erstellt</th>
                        </tr>
                    </thead>
                    <tbody>
                        {auftraege.map(auftrag => (
                            <tr key={auftrag.id} style={{ borderBottom: '1px solid #eee' }}>
                                <td style={{ padding: '0.75rem' }}>
                                    <a href={`/auftraege/${auftrag.id}/`}>{auftrag.id}</a>
                                </td>
                                <td style={{ padding: '0.75rem' }}>{auftrag.titel}</td>
                                <td style={{ padding: '0.75rem' }}>{auftrag.objekt.name}</td>
                                <td style={{ padding: '0.75rem' }}>{auftrag.kreditor.name}</td>
                                <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                                    <span style={{
                                        padding: '0.25rem 0.75rem',
                                        backgroundColor: STATUS_FARBEN[auftrag.status],
                                        color: 'white',
                                        borderRadius: '4px',
                                        fontSize: '0.9em',
                                    }}>
                                        {auftrag.status}
                                    </span>
                                </td>
                                <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                                    {auftrag.geschaetzte_kosten ? `${auftrag.geschaetzte_kosten} EUR` : '—'}
                                </td>
                                <td style={{ padding: '0.75rem', fontSize: '0.9em' }}>
                                    {new Date(auftrag.created_at).toLocaleDateString('de-DE')}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            
            {auftraege.length === 0 && !loading && (
                <p style={{ textAlign: 'center', color: '#999' }}>Keine Aufträge gefunden.</p>
            )}
        </div>
    );
}
```

**Smoke-Test Kriterium:**
- Dashboard lädt ohne Fehler
- Filter funktioniert korrekt (Status, Priorität, Suche)
- Aufträge sind in Tabelle sichtbar
- Statusfarbcodierung sichtbar

---

---

## HALT-Gate vor Live-Deployment

✋ **Vor Production-Freischaltung:**

1. **E-Mail-Konfiguration testen**
   - Ist `rechnungen@demme-immo.de` korrekt konfiguriert?
   - Sind Admin-E-Mail-Adressen hinterlegt?
   - Funktioniert lokaler E-Mail-Versand?

2. **Token-Sicherheit verifizieren**
   - Tokens sind genuinely zufällig (`secrets.token_urlsafe(48)`)
   - Token-URLs sind HTTPS-only
   - Tokens laufen nach 14 Tagen ab

3. **UI-Tests**
   - Handwerker können Auftrag annehmen/ablehnen
   - Admin sieht aktualisierte Status
   - Dashboard-Filter funktionieren

4. **GoBD-Konformität**
   - `created_at` + `updated_at` auf allen Entitäten
   - Keine Löschungen, nur Status-Änderungen
   - Audit-Trail in `angenommen_am`, `abgelehnt_am`, etc.

---

## Acceptance Criteria

✅ **Phase A–F erfolgreich, wenn:**

**Phase A (Migrationen):**
- [ ] Alle Migrationen fehlerfrei ausgeführt
- [ ] `python manage.py check` bestätigt keine Fehler
- [ ] Kreditor-Modell hat `gewerk` + `ist_handwerker`
- [ ] WEGObjekt-Modell hat M2M zu Kreditor via `WEGObjektHandwerker`
- [ ] Handwerkerauftrag-Modell vollständig
- [ ] AuftragsbestätigungsToken-Modell vollständig

**Phase B (Admin):**
- [ ] Kreditor-Admin zeigt Gewerk + ist_handwerker Felder
- [ ] WEGObjekt-Admin zeigt Handwerker-Inline mit Prioritätsordnung
- [ ] Handwerker können pro Objekt sortiert zugeordnet werden

**Phase C (Auftrag erstellen):**
- [ ] Vorgang-Detail hat Button "Handwerker beauftragen"
- [ ] Modal öffnet mit Kreditor-Auswahl (filtert nach ist_handwerker=True)
- [ ] Auftrag wird angelegt mit Status `entwurf` → `versendet`
- [ ] Token werden generiert (accept_token + reject_token)
- [ ] E-Mail wird versendet an Handwerker

**Phase D (Accept/Reject):**
- [ ] Handwerker klickt Accept-Link → Status auf `angenommen`
- [ ] Handwerker klickt Reject-Link → Status auf `abgelehnt` + optional Grund
- [ ] Admin-E-Mail mit Bestätigung versendet
- [ ] Token-Gültigkeit respektiert:
  - [ ] Dringend: 3 Businessdays
  - [ ] Normal: 7 Businessdays
  - [ ] Niedrig: 14 Businessdays
  - [ ] Sa/So/Feiertage werden übersprungen

**Phase E (Rechnungsverkettung):**
- [ ] Handwerker sendet Rechnung per Mail an `rechnungen@demme-immo.de`
- [ ] Mail-Intake-Pipeline erkennt Auftrag-ID im Betreff/Body
- [ ] `Handwerkerauftrag.rechnung_dokument` wird automatisch verlinkt
- [ ] Status wird ggf. auf `abgeschlossen` aktualisiert
- [ ] Auftrag-Detail zeigt verlinkte Rechnung

**Phase F (Dashboard):**
- [ ] Dashboard zeigt alle Aufträge mit Filtration
- [ ] Filter funktionieren: Status, Objekt, Handwerker, Priorität, Suche
- [ ] Status-Historie sichtbar (created_at, angenommen_am, abgelehnt_am, rechnung_eingegangen_am)
- [ ] Statusfarbcodierung korrekt
- [ ] Pagination funktioniert (für >50 Aufträge)

---

## Nächste Phasen (future, nicht in v1.0)

- **Phase G:** Automatisierte Auftrags-Vergabe basierend auf Regeln (Vorgangstyp, Kosten, Kategorie)
- **Phase H:** Handwerker-Portal mit Login (Auftragshistorie, Rechnungshistorie)
- **Phase I:** SMS/WhatsApp-Benachrichtigungen als Fallback
- **Phase J:** Rechnungs-Matching: Handwerker-Rechnung auto-buchen auf Kreditor (Sollstellung → OP)

---

## Claude Code – Orchestrator Prompt

```
Deine Aufgabe: Implementiere Handwerkerauftrag-Management nach 
CLAUDE_CODE_ANLEITUNG_HANDWERKERAUFTRAG_v1_0.md

Schritte:
1. Phase A: Alle Migrationen schreiben
2. Phase B: Admin-Interfaces erweitern
3. Phase C: API-Endpoint & E-Mail-Versand
4. Phase D: Public Accept/Reject Views (mit Businessdays-Logik)
5. Phase E: Rechnungsverkettung via Mail-Intake-Integration
6. Phase F: Dashboard (React) mit Filtration

Agents:
- immo-explorer (Haiku): Verifiziere bestehende Kreditor/WEGObjekt/Dokument/Mail-Intake Struktur
- immo-builder (Sonnet): Implementiere alle Phasen sequenziell
- immo-architect (Opus): Bei Blocker/Mehrdeutigkeiten eskalieren

Dependencies vor Start:
- python-holidays installieren
- Mail-Intake-Pipeline aktiv & getestet

Pausen zwischen Phasen für Patrik-Feedback.
Keine autonomen Migrationen ohne "run"-Befehl.

Token-Gültigkeiten dringend 100% validieren (Businessdays + Feiertage).

Status: Bereit zur Implementierung.
```
