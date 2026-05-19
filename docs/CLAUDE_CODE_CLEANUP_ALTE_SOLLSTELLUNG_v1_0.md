# Claude Code – Anleitung: Cleanup der alten Sollstellungs-Welt (IMMOCORE)

**Version:** 1.0
**Status:** Implementierungsreif — kritisch (alter Code-Pfad bucht aktuell weiter auf `41900` bei Sollstellung, was die Kassenprinzip-Architektur des Nebenbuchs umgeht)
**Bezug:** Schließt die in Hausgeld-Nebenbuch v1.1 in Kap. 13 vorgesehenen,
aber nicht durchgeführten Greenfield-Cleanup-Schritte ab.

---

## 1. Ausgangslage

Im Zuge der Implementierung von Hausgeld-Nebenbuch v1.1 wurde die **neue
Welt** komplett angelegt:

- `HausgeldSollstellungslauf`, `HausgeldSollstellung`, `SollstellungSplit`,
  `SollstellungZahlung`, `OposSequenz` (Modelle)
- `sollstellung_service.py`, `sollstellungslauf_service.py`,
  `opos_nr_service.py` (Services)
- `HausgeldSollstellungslaufViewSet`, `HausgeldSollstellungViewSet` (Views)
- URL-Routes `hg-laeufe`, `hg-sollstellungen`

**Die alte Welt wurde jedoch nicht entfernt** und ist die einzige, die
vom Frontend aufgerufen wird:

| Schicht | Alte Welt (lebt) | Neue Welt (verwaist) |
|---|---|---|
| Modelle | `SollstellungsLauf` (`models.py:235`), `Sollstellung` (`models.py:289`) | `HausgeldSollstellungslauf`, `HausgeldSollstellung`, ... |
| Service | `services/sollstellung.py` (bucht `0001.900 / 41900` bei Sollstellung) | `services/sollstellung_service.py`, `services/sollstellungslauf_service.py` |
| ViewSets | `SollstellungsLaufViewSet`, `SollstellungViewSet` | `HausgeldSollstellungslaufViewSet`, `HausgeldSollstellungViewSet` |
| URL-Routes | `/sollstellungslaeufe/`, `/sollstellungen/` | `/hg-laeufe/`, `/hg-sollstellungen/` |
| Frontend-API | `api/buchhaltung.ts → sollstellungslaeufe(...)`, `api/zahlungsverkehr.ts → sollstellungslaeufe(...)` | – |
| Frontend-Pages | `pages/buchhaltung/Sollstellungen.tsx`, `pages/zahlungsverkehr/Lastschrift.tsx` | – |

**Konsequenz:** Jeder vom Frontend gestartete Sollstellungslauf erzeugt
nach wie vor Sachkontenbuchungen `0001.900 an 41900` (Soll-Prinzip
verletzt das Kassenprinzip §28 WEG, weil Erlös vor Geldeingang gebucht
wird).

## 2. Lücke im neuen Backend

Die alte `SollstellungViewSet`-Welt bot einen **dreistufigen Workflow**:

1. `POST /sollstellungslaeufe/simulieren/` → Vorschau ohne DB-Commit
2. `POST /sollstellungslaeufe/` → Lauf anlegen (Status `vorschau`)
3. `POST /sollstellungslaeufe/{id}/freigeben/` → Freigabe (Vier-Augen)
4. `POST /sollstellungslaeufe/{id}/ausfuehren/` → Buchung & Sollstellungen erzeugen

Der neue `HausgeldSollstellungslaufViewSet` ruft direkt
`run_hausgeld_monat` auf — ein **einstufiger Commit ohne Vorschau und
ohne Freigabe**.

Beim Cleanup muss diese Funktionalität nachgezogen werden, sonst geht
der Vier-Augen-Workflow verloren.

## 3. Migrationsstrategie

Reihenfolge der Schritte (jeder Schritt muss laufen, bevor der nächste
beginnt — sonst brechen Importe oder Frontend):

```
Phase A — Backend Vorschau-/Freigabe-Workflow ergänzen
  Schritt 1  Service: vorschau-Funktion
  Schritt 2  Service: status-Lebenszyklus (vorschau → freigegeben → commited)
  Schritt 3  ViewSet: simulieren/freigeben/commiten als @action

Phase B — Frontend umstellen
  Schritt 4  api/buchhaltung.ts auf hg-laeufe umstellen
  Schritt 5  api/zahlungsverkehr.ts auf hg-laeufe umstellen
  Schritt 6  Pages Sollstellungen.tsx + Lastschrift.tsx auf neue Strukturen umstellen

Phase C — Lastschriftlauf umbauen
  Schritt 7  Lastschriftlauf-View liest aus HausgeldSollstellungslauf statt SollstellungsLauf

Phase D — Alte Welt entfernen
  Schritt 8  Views/Serializers/URLs der alten Welt löschen
  Schritt 9  Service services/sollstellung.py löschen
  Schritt 10 Modelle SollstellungsLauf + Sollstellung löschen
  Schritt 11 Migration für Modell-Löschung erzeugen

Phase E — Verifikation
  Schritt 12 Smoke-Test laut Akzeptanzkriterien
```

Hinweis: Phase B kann erst beginnen, wenn die Endpunkte aus Phase A
existieren. Phase D darf erst starten, wenn Phase B und C komplett
durch sind, sonst läuft das Frontend ins Leere.

---

## 4. Phase A — Vorschau-/Freigabe-Workflow im neuen Backend

### Schritt 1 — Service: `simuliere_hausgeld_monat`

Datei: `apps/buchhaltung/services/sollstellungslauf_service.py`

Neue Funktion **vor** `run_hausgeld_monat`:

```python
def simuliere_hausgeld_monat(objekt, periode: date) -> dict:
    """
    Erzeugt eine Vorschau für den Hausgeld-Massenlauf ohne DB-Commit.
    Listet pro aktivem EigentumsVerhältnis die zu erwartenden Splits
    und Summen.

    Return-Format:
    {
      'objekt_id':   <uuid>,
      'periode':     '2026-03',
      'anzahl_evs':  17,
      'gesamtsumme': '6420.00',
      'positionen': [
        {
          'eigentumsverhaeltnis_id': <uuid>,
          'eigentuemer_name':        'Müller, Hans',
          'einheit_nr':              'WE01',
          'splits': [
            {'ba_code': '900', 'betrag': '250.00'},
            {'ba_code': '911', 'betrag': '80.00'},
          ],
          'summe':       '330.00',
          'opos_nr_neu': '100001000045829-7'  # nur informativ, wird erst bei Commit reserviert
        },
        ...
      ],
      'warnungen': [
        # Eigentümer ohne Hausgeld-Beträge in der Historie etc.
      ]
    }
    """
    # Iteriert über aktive EVs analog run_hausgeld_monat,
    # aber legt KEINE Datensätze an.
    # Bestehende Hilfsfunktion `aktuelle_hausgeld_betraege` wiederverwenden.
```

Nichts wird persistiert. Frontend kann auf dieser Basis Vorschau
darstellen, Benutzer klickt anschließend „Bestätigen".

### Schritt 2 — Status-Lebenszyklus am `HausgeldSollstellungslauf`

Datei: `apps/buchhaltung/models.py` — Modell `HausgeldSollstellungslauf`.

Falls noch nicht vorhanden, `status`-Feld mit Werten:

```python
STATUS_CHOICES = [
    ('vorschau',    'Vorschau'),
    ('freigegeben', 'Freigegeben (Vier-Augen)'),
    ('commited',    'Commited / Ausgeführt'),
    ('storniert',   'Storniert'),
]
status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vorschau')
freigabe_user = models.ForeignKey(
    settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    related_name='freigegebene_hausgeld_laeufe'
)
freigegeben_am = models.DateTimeField(null=True, blank=True)
```

Service `run_hausgeld_monat` so anpassen, dass er **nur dann** läuft,
wenn `lauf.status == 'freigegeben'` (Übergang `freigegeben → commited`).
Direkt-Commit für Tests/Migrationen über Parameter `skip_freigabe=True`
weiterhin möglich.

Neue Service-Funktionen:

```python
@transaction.atomic
def erstelle_lauf_aus_vorschau(objekt, periode, user) -> HausgeldSollstellungslauf:
    """Legt Lauf-Datensatz mit Status='vorschau' an, ohne Sollstellungen."""

@transaction.atomic
def freigeben_lauf(lauf, user) -> HausgeldSollstellungslauf:
    """vorschau → freigegeben. Validiert: freigabe_user != erstellt_von."""

@transaction.atomic
def commiten_lauf(lauf, user) -> HausgeldSollstellungslauf:
    """freigegeben → commited. Ruft run_hausgeld_monat-Kern auf."""
```

### Schritt 3 — ViewSet-Actions

Datei: `apps/buchhaltung/views.py` — `HausgeldSollstellungslaufViewSet`.

Vier neue `@action`-Methoden:

```python
@action(detail=False, methods=['post'], url_path='simulieren')
def simulieren(self, request):
    objekt_id = request.data.get('objekt_id')
    periode   = parse_date(request.data.get('periode'))  # 'YYYY-MM' → 1.+Monatserster
    objekt    = Objekt.objects.get(pk=objekt_id)
    vorschau  = simuliere_hausgeld_monat(objekt, periode)
    return Response(vorschau)

@action(detail=False, methods=['post'], url_path='erstellen')
def erstellen(self, request):
    """Erzeugt Lauf-Datensatz im Status 'vorschau' aus einer Simulation."""
    objekt = Objekt.objects.get(pk=request.data['objekt_id'])
    periode = parse_date(request.data['periode'])
    lauf = erstelle_lauf_aus_vorschau(objekt, periode, request.user)
    return Response(HausgeldSollstellungslaufSerializer(lauf).data,
                    status=status.HTTP_201_CREATED)

@action(detail=True, methods=['post'], url_path='freigeben')
def freigeben(self, request, pk=None):
    lauf = self.get_object()
    lauf = freigeben_lauf(lauf, request.user)
    return Response(HausgeldSollstellungslaufSerializer(lauf).data)

@action(detail=True, methods=['post'], url_path='commiten')
def commiten(self, request, pk=None):
    lauf = self.get_object()
    lauf = commiten_lauf(lauf, request.user)
    return Response(HausgeldSollstellungslaufSerializer(lauf).data)
```

Der bisherige `lauf_starten`-Endpoint (sofern vorhanden) bleibt
übergangsweise erhalten und wird in Phase D entfernt, sobald das
Frontend umgestellt ist.

---

## 5. Phase B — Frontend umstellen

### Schritt 4 — `api/buchhaltung.ts` umstellen

Datei: `frontend/src/api/buchhaltung.ts`

Alte Funktion ersetzen — alle 5 Aufrufe von `/sollstellungslaeufe/`:

```typescript
// VORHER
sollstellungslaeufe: (objektId?: string) =>
  client.get<SollstellungsLauf[]>('/sollstellungslaeufe/', { params: ... })
simulieren: (data) => client.post('/sollstellungslaeufe/simulieren/', data)
erstellen: (data) => client.post<SollstellungsLauf>('/sollstellungslaeufe/', data)
freigeben: (id) => client.post(`/sollstellungslaeufe/${id}/freigeben/`)
ausfuehren: (id) => client.post(`/sollstellungslaeufe/${id}/ausfuehren/`)

// NACHHER
hausgeldLaeufe: (objektId?: string) =>
  client.get<HausgeldSollstellungslauf[]>('/hg-laeufe/', { params: ... })
simulierenHausgeld: (data: {objekt_id: string; periode: string}) =>
  client.post('/hg-laeufe/simulieren/', data)
erstellenHausgeld: (data: {objekt_id: string; periode: string}) =>
  client.post<HausgeldSollstellungslauf>('/hg-laeufe/erstellen/', data)
freigebenHausgeld: (id: string) =>
  client.post(`/hg-laeufe/${id}/freigeben/`)
commitenHausgeld: (id: string) =>
  client.post(`/hg-laeufe/${id}/commiten/`)
stornierenHausgeld: (id: string, grund: string) =>
  client.post(`/hg-laeufe/${id}/stornieren/`, { grund })
```

TypeScript-Typen `SollstellungsLauf` durch `HausgeldSollstellungslauf`
ersetzen. Felder-Mapping siehe `serializers.py:366`
(`HausgeldSollstellungslaufSerializer`).

### Schritt 5 — `api/zahlungsverkehr.ts` umstellen

Datei: `frontend/src/api/zahlungsverkehr.ts`

Der einzige `sollstellungslaeufe`-Aufruf hier wird vom
Lastschrift-Wizard verwendet. Umstellen auf:

```typescript
hausgeldLaeufe: (params?: Record<string, string>) =>
  client.get<HausgeldSollstellungslauf[]>('/hg-laeufe/', { params }).then(r => r.data)
```

Frontend-Code, der das Resultat verarbeitet, muss bei Lastschrift-
Generierung nun `HausgeldSollstellungslauf.sollstellungen[].splits[]`
auflösen (siehe Phase C).

### Schritt 6 — Pages umstellen

**Datei: `frontend/src/pages/buchhaltung/Sollstellungen.tsx`**

Alle Aufrufe und queryKeys umstellen:

```typescript
// VORHER
queryKey: ['sollstellungslaeufe', objektId],
queryFn: () => buchhaltungApi.sollstellungslaeufe(objektId ?? undefined),

// NACHHER
queryKey: ['hg-laeufe', objektId],
queryFn: () => buchhaltungApi.hausgeldLaeufe(objektId ?? undefined),
```

UI-Anpassungen:

- Spalte „Status": neue Werte `vorschau / freigegeben / commited / storniert`
- Button-Beschriftung: „Ausführen" → „Commiten"
- Nach Commit: invalidateQueries für `hg-laeufe` und `hg-sollstellungen`
- Detail-Ansicht eines Laufs: zeige Sollstellungen mit OPOS-Nr.,
  klickbar auf die Detail-Ansicht der einzelnen Sollstellung
  (`/hg-sollstellungen/{id}/`)

**Datei: `frontend/src/pages/zahlungsverkehr/Lastschrift.tsx`**

```typescript
// VORHER
queryKey: ['sollstellungslaeufe', objektId],
queryFn: () => zahlungsverkehrApi.sollstellungslaeufe(objektId ? { objekt: objektId } : {}),

// NACHHER
queryKey: ['hg-laeufe', objektId],
queryFn: () => zahlungsverkehrApi.hausgeldLaeufe(objektId ? { objekt: objektId } : {}),
```

Wichtig: Filter `?status=commited` setzen — nur fertig gebuchte Läufe
können zur Lastschrift herangezogen werden.

---

## 6. Phase C — Lastschriftlauf umbauen

### Schritt 7 — `views.py` Lastschriftlauf auf Nebenbuch umstellen

Datei: `apps/buchhaltung/views.py`, Zeilen ca. 1080–1190
(bestehende Lastschriftlauf-Action).

**Bestehender Code (auszug):**

```python
sollstellungs_lauf = SollstellungsLauf.objects.prefetch_related(
    'sollstellungen__personenkonto__eigentuemer__sepa_mandat'
).get(id=sollstellungs_lauf_id, objekt=objekt)
...
for s in sollstellungs_lauf.sollstellungen.filter(status__in=('vorschau', 'gebucht')):
    ...
```

**Umstellung:**

```python
hg_lauf = HausgeldSollstellungslauf.objects.prefetch_related(
    'sollstellungen__splits',
    'sollstellungen__eigentumsverhaeltnis__person__sepa_mandat',
).get(id=hg_lauf_id, objekt=objekt)

if hg_lauf.status != 'commited':
    return Response(
        {'error': f'Hausgeld-Lauf hat Status "{hg_lauf.status}" — nur "commited" erlaubt'},
        status=status.HTTP_400_BAD_REQUEST
    )

positionen = []
ohne_mandat = []

for ss in hg_lauf.sollstellungen.filter(status_cached__in=('offen', 'teilbezahlt'),
                                          storniert_am__isnull=True):
    person = ss.eigentumsverhaeltnis.person
    if not person.sepa_mandat or not person.sepa_mandat.aktiv:
        ohne_mandat.append({'sollstellung_id': str(ss.id), 'grund': 'Kein aktives SEPA-Mandat'})
        continue

    # Pro Sollstellung gemäß Spec Kap. 9.2: Splits nach Zielbankkonto gruppieren
    splits_je_bank = {}
    if ss.sollstellungs_typ == 'hausgeld':
        for split in ss.splits.all():
            splits_je_bank.setdefault(split.bankkonto_ziel_id, []).append(split)
    else:
        # Sonderumlage / Abrechnungsergebnis: kein Split, eigenes Zielbankkonto am Eltern
        splits_je_bank[ss.zielbankkonto_id] = [None]  # Marker: keine Split-Aufteilung

    # Pro Zielbankkonto eine Lastschriftposition mit EndToEndId-Suffix
    for bankkonto_id, splits in splits_je_bank.items():
        if ss.sollstellungs_typ == 'hausgeld':
            betrag = sum(s.betrag for s in splits)
            suffix = bestimme_suffix(bankkonto_id, ss.objekt)  # 'B' oder 'R{n}'
        elif ss.sollstellungs_typ == 'sonderumlage':
            betrag = ss.soll_betrag
            suffix = 'S'
        else:  # abrechnungsergebnis
            betrag = ss.soll_betrag
            suffix = 'A'

        positionen.append({
            'sollstellung_id': str(ss.id),
            'end_to_end_id':   f"{ss.opos_nr}-{suffix}",
            'betrag':          betrag,
            'mandat':          person.sepa_mandat,
            'iban':            person.sepa_mandat.iban,
            'name':            person.anzeigename,
            'verwendungszweck': baue_verwendungszweck(ss, suffix),  # menschenlesbar, ohne OPOS-Nr.
        })
```

Hilfsfunktion in `services/sepa_lastschrift.py`:

```python
def bestimme_suffix(bankkonto_id, objekt) -> str:
    """
    'B' für Bewirtschaftungskonto, 'R{n}' für Rücklagenkonto Nr. n.
    n entspricht Bankkonto.reihenfolge - 1 (Rücklage 1 = R1, ...).
    """
    bk = Bankkonto.objects.get(pk=bankkonto_id)
    if bk.konto_typ == 'bewirtschaftung':
        return 'B'
    elif bk.konto_typ == 'ruecklage':
        return f'R{bk.reihenfolge - 1}'  # reihenfolge 2 → R1, 3 → R2
    raise ValueError(f"Unbekannter Bankkonto-Typ: {bk.konto_typ}")


def baue_verwendungszweck(ss, suffix) -> str:
    """
    Menschenlesbar, ohne OPOS-Nr.
    Format: {Zweck} {Periode} - {Einheit_Nr} - Objekt {Objekt_Kurzbez}
    """
    einheit_nr = ss.eigentumsverhaeltnis.einheit.einheit_nr
    objekt_kurz = ss.objekt.kurzbezeichnung or ss.objekt.bezeichnung
    periode_str = ss.periode.strftime('%m/%Y')

    if ss.sollstellungs_typ == 'hausgeld':
        zweck = 'Rücklage' if suffix.startswith('R') else 'Hausgeld'
    elif ss.sollstellungs_typ == 'sonderumlage':
        zweck = f'Sonderumlage {ss.bezeichnung or ""}'.strip()
    else:
        zweck = f'Abrechnung {ss.periode.year}'

    return f"{zweck} {periode_str} - {einheit_nr} - Objekt {objekt_kurz}"
```

---

## 7. Phase D — Alte Welt entfernen

> **WICHTIG:** Diese Phase darf erst beginnen, wenn Phase B + C komplett
> durch sind und das Frontend nachweislich gegen die neuen Endpoints
> arbeitet. Test vorher: einmal manuell einen Hausgeldlauf via Frontend
> durchspielen (Simulieren → Erstellen → Freigeben → Commiten →
> Lastschriftlauf), prüfen dass keine `41xxx`-Buchung entstanden ist.

### Schritt 8 — Views, Serializers, URLs entfernen

Datei: `apps/buchhaltung/views.py`

Löschen:
- Zeile 46: `from .services.sollstellung import simuliere_lauf, fuehre_lauf_aus`
- Zeile 190–248: Klasse `SollstellungsLaufViewSet` komplett
- Zeile 251–280: Klasse `SollstellungViewSet` komplett
- Imports am Dateianfang: `SollstellungsLauf, Sollstellung,` aus Modul-Import entfernen
- Imports am Dateianfang: `SollstellungsLaufSerializer, SollstellungSerializer,` aus Serializer-Import entfernen

Datei: `apps/buchhaltung/serializers.py`

Löschen:
- Zeile 135–145: Klasse `SollstellungsLaufSerializer`
- Zeile 147–308: Klasse `SollstellungSerializer` (inkl. `get_sollstellungs_lauf_info`)
- Imports am Dateianfang: `SollstellungsLauf, Sollstellung,` entfernen

Datei: `apps/buchhaltung/urls.py`

Löschen:
- Imports: `SollstellungsLaufViewSet, SollstellungViewSet,`
- Zeile 25: `router.register(r'sollstellungslaeufe', SollstellungsLaufViewSet, ...)`
- Zeile 26: `router.register(r'sollstellungen', SollstellungViewSet, ...)`

### Schritt 9 — Service `services/sollstellung.py` löschen

```bash
git rm apps/buchhaltung/services/sollstellung.py
```

Prüfen, dass kein anderer Code mehr darauf importiert:

```powershell
Select-String -Path apps -Recurse -Include *.py -Pattern "from.*services\.sollstellung\s+import|from\s+\.services\.sollstellung\s+import"
```

Erwartung: kein Treffer mehr. Falls doch — diese Stellen ebenfalls
korrigieren.

### Schritt 10 — Modelle `SollstellungsLauf` und `Sollstellung` löschen

Datei: `apps/buchhaltung/models.py`

Löschen:
- Klasse `SollstellungsLauf` (Zeile ca. 235–286)
- Klasse `Sollstellung` (Zeile ca. 289–338)

Achtung: In Zeile 867 referenziert ein anderes Modell
`sollstellungs_lauf = models.ForeignKey(SollstellungsLauf, ...)` —
das ist vermutlich `Lastschriftlauf` (siehe Migration 0012). Dieses Feld
muss durch `hausgeld_sollstellungslauf = models.ForeignKey(HausgeldSollstellungslauf, ...)`
ersetzt werden, **nachdem** der Lastschriftlauf-Code aus Phase C
umgestellt ist und die UI ohne den alten FK auskommt.

### Schritt 11 — Migration erzeugen

```bash
python manage.py makemigrations buchhaltung -n drop_alte_sollstellung_welt
```

Die generierte Migration sollte enthalten:
- `migrations.RemoveField(...)` für `Lastschriftlauf.sollstellungs_lauf`
- `migrations.DeleteModel('Sollstellung')`
- `migrations.DeleteModel('SollstellungsLauf')`
- `migrations.AddField(...)` für `Lastschriftlauf.hausgeld_sollstellungslauf` (neu)

Generierte Datei prüfen (Reihenfolge — der `RemoveField` muss **vor**
den `DeleteModel`-Anweisungen stehen, sonst kollidiert der Foreign Key).

```bash
python manage.py migrate buchhaltung
```

---

## 8. Phase E — Verifikation

### Schritt 12 — Smoke-Test

End-to-End-Durchlauf gegen das Test-Objekt (das du auch beim
Nebenbuch-Smoke-Test verwendet hast):

| Nr | Aktion | Erwartung |
|---|---|---|
| 1 | Frontend → Sollstellungen → „Simulieren" für März 2026 | Vorschau-Liste mit allen EVs, korrekten Splits, OPOS-Nr.-Indikation |
| 2 | „Erstellen" klicken | Lauf entsteht mit Status `vorschau`; **DB-Query: `SELECT COUNT(*) FROM buchhaltung_buchungssatz WHERE konto_id IN (Konten mit 41xxx)` → unverändert** |
| 3 | Anderer User (oder gleicher mit Demo-Rolle) → „Freigeben" | Status `freigegeben`, `freigabe_user` und `freigegeben_am` gesetzt |
| 4 | „Commiten" klicken | Status `commited`, alle Hausgeld-Sollstellungen + Splits + OPOS-Nrn. entstehen. **DB-Query erneut: keine `41xxx`-Buchungen entstanden.** |
| 5 | DB-Check: `SELECT COUNT(*) FROM buchhaltung_hausgeldsollstellung WHERE sollstellungslauf_id = <lauf-id>` | Anzahl = Anzahl aktiver EVs des Objekts |
| 6 | Frontend → Zahlungsverkehr → Lastschrift → Lauf auswählen | Liste der commiteten Hausgeld-Läufe erscheint |
| 7 | Lastschrift generieren | pain.008-XML mit korrekten EndToEndIds (Suffix `-B` / `-R{n}`) |
| 8 | camt.053-Test-Datei mit Zahlungseingang einspielen | **JETZT** entsteht eine Buchung `Soll 18000 / Haben 41900` (+ ggf. 41911 etc.) — geprüft per DB-Query |
| 9 | URL-Check: `GET /api/v1/sollstellungslaeufe/` | HTTP 404 (Route nicht mehr vorhanden) |
| 10 | URL-Check: `GET /api/v1/hg-laeufe/` | HTTP 200 |

Wenn alle 10 Punkte grün sind, ist der Cleanup vollständig.

---

## 9. Hinweis zur Reihenfolge bei Claude Code

> **Hinweis an Claude Code:** Diese Anleitung ist linear strukturiert,
> aber Phase A muss **komplett** durch sein (Tests grün), bevor Phase B
> beginnt. Phase B muss komplett durch sein (Frontend baut und ein
> manueller Klick durch den Wizard funktioniert), bevor Phase C startet.
> Phase D ist **erst zulässig**, wenn ein End-to-End-Durchlauf laut
> Smoke-Test Punkt 1–8 erfolgreich war. Andernfalls bleibt das Frontend
> mit toten Routen zurück.
>
> Bei Unsicherheiten in Phase C (Lastschriftlauf-Umstellung) lieber
> einen Zwischen-Commit machen und Rücksprache halten — das ist die
> einzige Phase, in der fachliche Logik geändert wird, nicht nur
> Code-Pfade umgebogen.

---

**Ende der Spezifikation.**
