import re
from datetime import date


IBAN_RE = re.compile(r'^DE\d{20}$')


def _validate_iban(iban: str) -> bool:
    cleaned = iban.replace(' ', '').upper()
    return bool(IBAN_RE.match(cleaned))


class ObjektAnlageValidator:
    """Validates individual wizard steps for the objekt_anlegen process (10 steps).

    Die Schrittnummern entsprechen SCHRITT_DEFINITIONEN['objekt_anlegen'] in
    prozesse/views.py und dem Frontend-Wizard:
      1 Objekttyp · 2 Stammdaten · 3 Eingänge · 4 Wirtschaftsjahr · 5 Einheiten ·
      6 Bankkonten · 7 Kontenrahmen · 8 Verträge · 9 Freigabelimits · 10 Review
    """

    def validate_step(self, nr: int, data: dict) -> list:
        method = getattr(self, f'_step_{nr}', None)
        if method is None:
            return []
        return method(data)

    def _step_1(self, data: dict) -> list:
        errors = []
        objekt_typ = data.get('objekt_typ', '')
        if not objekt_typ:
            errors.append('Objekttyp ist erforderlich.')
        elif objekt_typ not in ('WEG', 'ZH', 'SEV'):
            errors.append(f'Objekttyp muss WEG, ZH oder SEV sein (erhalten: {objekt_typ}).')
        return errors

    def _step_2(self, data: dict) -> list:
        errors = []
        for field, label in [
            ('bezeichnung', 'Bezeichnung'), ('strasse', 'Straße'), ('plz', 'PLZ'),
            ('ort', 'Ort'), ('verwaltung_seit', 'Verwaltung seit'),
            ('wirtschaftsjahr_start', 'Wirtschaftsjahr-Start'),
        ]:
            if not str(data.get(field, '') or '').strip():
                errors.append(f'{label} ist erforderlich.')
        return errors

    def _step_3(self, data: dict) -> list:
        errors = []
        eingaenge = data.get('eingaenge', [])
        if not eingaenge:
            errors.append('Mindestens ein Eingang ist erforderlich.')
            return errors
        if sum(1 for e in eingaenge if e.get('ist_hauptadresse')) != 1:
            errors.append('Genau ein Eingang muss als Hauptadresse markiert sein.')
        return errors

    # Step 4 — Wirtschaftsjahr
    def _step_4(self, data: dict) -> list:
        errors = []
        jahr = data.get('jahr')
        try:
            jahr_int = int(jahr)
        except (TypeError, ValueError):
            errors.append('Wirtschaftsjahr ist erforderlich.')
            return errors
        max_jahr = date.today().year + 1
        if jahr_int < 2000 or jahr_int > max_jahr:
            errors.append(f'Wirtschaftsjahr muss zwischen 2000 und {max_jahr} liegen (erhalten: {jahr_int}).')
        return errors

    # Step 5 — Einheiten (Wohnungsbezeichnungen eindeutig)
    def _step_5(self, data: dict) -> list:
        errors = []
        seen: set = set()
        for e in data.get('einheiten', []):
            bez = e.get('wohnungsbezeichnung', '')
            if bez and bez in seen:
                errors.append(f'Wohnungsbezeichnung "{bez}" ist doppelt vorhanden.')
            seen.add(bez)
        return errors

    # Step 6 — Bankkonten (IBAN/BIC/Kontoinhaber optional, nur Bezeichnung Pflicht)
    def _step_6(self, data: dict) -> list:
        errors = []
        bankkonten = data.get('bankkonten', [])
        bew = [b for b in bankkonten if b.get('konto_typ') == 'bewirtschaftung']
        if len(bew) != 1:
            errors.append(f'Genau ein Bewirtschaftungskonto ist erforderlich (aktuell: {len(bew)}).')
        elif not str(bew[0].get('bezeichnung', '') or '').strip():
            errors.append('Bezeichnung des Bewirtschaftungskontos ist erforderlich.')
        for b in bankkonten:
            if b.get('konto_typ') == 'ruecklage' and not str(b.get('bezeichnung', '') or '').strip():
                errors.append('Bezeichnung jedes Rücklagenkontos ist erforderlich.')
        # IBAN nur validieren wenn angegeben
        ibans_seen: set = set()
        for b in bankkonten:
            iban = (b.get('iban', '') or '').replace(' ', '').upper()
            if iban:
                if not _validate_iban(iban):
                    errors.append(f'IBAN ungültig: {iban}')
                elif iban in ibans_seen:
                    errors.append(f'IBAN {iban} ist doppelt vorhanden.')
                else:
                    ibans_seen.add(iban)
        return errors

    # Step 7 — Kontenrahmen (immer gültig)
    def _step_7(self, data: dict) -> list:
        return []

    # Step 8 — Verträge (optional, immer gültig)
    def _step_8(self, data: dict) -> list:
        return []

    # Step 9 — Freigabelimits
    def _step_9(self, data: dict) -> list:
        errors = []
        if not data.get('grenzen'):
            errors.append('Mindestens eine Freigabegrenze ist erforderlich.')
        return errors

    # Step 10 — Review & Aktivierung (immer gültig)
    def _step_10(self, data: dict) -> list:
        return []
