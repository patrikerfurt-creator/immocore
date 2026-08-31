import client from './client'

// Wizard-API Jahresabrechnung (HGA-Spec v1.0 Kap. 9)

export interface Jahresabrechnung {
  id: string
  objekt: string
  objekt_bezeichnung: string
  wirtschaftsjahr: string
  wirtschaftsjahr_jahr: number
  erstellungsdatum: string
  status: 'entwurf' | 'freigegeben' | 'gesperrt'
  current_step: number
  freigegeben_am: string | null
  freigegeben_von_name: string | null
  sollstellungslauf: string | null
}

export interface SchrittResponse {
  jahresabrechnung: Jahresabrechnung
  schritt: number
  current_step: number
  steps_data: Record<string, unknown> | null
  daten: Record<string, unknown>
}

export interface KreditorOpZeile {
  op_nummer: number
  kreditor: string
  betrag_offen: string
  faellig_ab: string
  status: string
  buchung_festgeschrieben: boolean
  vorgetragen_nach: number | null
}

export interface KreditorVortragResponse {
  vorgetragen_nach: number
  anzahl: number
  anzahl_gebucht: number
  summe: string
  ops: Array<{
    op_nummer: number
    kreditor: string
    betrag: string
    gebucht: boolean
    hinweis: string
  }>
  pruefung: {
    blockiert: boolean
    kreditor_ops: KreditorOpZeile[]
    vorgetragene_ops: KreditorOpZeile[]
  }
}

export interface KostenstellenPosition {
  konto_id: string
  kontonummer: string
  kontoname: string
  ist: string
  plan: string | null
  abweichung: string | null
  abweichung_prozent: string | null
}

export interface KostenstellenResponse {
  wirtschaftsplan_vorhanden: boolean
  positionen: KostenstellenPosition[]
  summe_ist: string
  summe_plan: string | null
}

export interface UmlageschluesselZeile {
  konto_id: string
  kontonummer: string
  kontoname: string
  vs_code: string | null
}

export interface UmlageschluesselResponse {
  konten: UmlageschluesselZeile[]
  vs_optionen: { code: string; label: string }[]
}

export interface Ruecklage {
  bankkonto_id: string
  bezeichnung: string
  ba_nr: string
  anfangsbestand: string
  zufuehrungen: string
  entnahmen: string
  endbestand_berechnet: string
  endbestand_bank: string
  abweichung: string
  klaerungsfall: boolean
  zufuehrung_plan: string | null
}

export interface EinzelAbrechnungPosition {
  kontonummer: string
  kontoname: string
  gesamtkosten: string
  vs_code: string | null
  anteil?: string
  betrag?: string
  fehler?: string
  manuell_korrigiert?: boolean
}

export interface EinzelAbrechnung {
  id: string
  einheit: string
  einheit_nr: string
  eigentuemer_name: string
  hausgeld_soll_gesamt: string
  kostenanteil_gesamt: string
  abrechnungsergebnis: string
  positionen: EinzelAbrechnungPosition[]
  ruecklagen: Record<string, string>[]
  hinweis_eigentuemerwechsel: boolean
  sollstellung: string | null
  dokument: string | null
}

export interface FreigabeResponse {
  jahresabrechnung: Jahresabrechnung
  guthaben_einheiten: number
  hinweis: string
}

const BASE = '/jahresabrechnungen'

export const jahresabrechnungApi = {
  list: (params?: Record<string, string>) =>
    client.get<Jahresabrechnung[]>(`${BASE}/`, { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Jahresabrechnung>(`${BASE}/${id}/`).then(r => r.data),

  // Schritt 1: anlegen (oder bestehenden Entwurf fortsetzen)
  create: (objektId: string, wirtschaftsjahrId: string) =>
    client.post<Jahresabrechnung>(`${BASE}/`, {
      objekt: objektId,
      wirtschaftsjahr: wirtschaftsjahrId,
    }).then(r => r.data),

  deleteEntwurf: (id: string) =>
    client.delete(`${BASE}/${id}/`),

  schritt: (id: string, nr: number) =>
    client.get<SchrittResponse>(`${BASE}/${id}/schritt/${nr}/`).then(r => r.data),

  schrittSpeichern: (id: string, nr: number, daten?: Record<string, unknown>) =>
    client.patch<SchrittResponse>(`${BASE}/${id}/schritt/${nr}/`, { daten }).then(r => r.data),

  kostenstellen: (id: string) =>
    client.get<KostenstellenResponse>(`${BASE}/${id}/kostenstellen/`).then(r => r.data),

  umlageschluessel: (id: string) =>
    client.get<UmlageschluesselResponse>(`${BASE}/${id}/umlageschluessel/`).then(r => r.data),

  umlageschluesselKorrigieren: (id: string, kontoId: string, vsCode: string) =>
    client.patch<UmlageschluesselResponse>(`${BASE}/${id}/umlageschluessel/`, {
      konto_id: kontoId,
      vs_code: vsCode,
    }).then(r => r.data),

  // VS-Zuordnung je Konto neu aus dem Kontenrahmen einlesen (Schritt 4)
  umlageschluesselNeuEinlesen: (id: string) =>
    client.post<{ konten_gesamt: number; zugeordnet: number }>(
      `${BASE}/${id}/umlageschluessel-neu-einlesen/`).then(r => r.data),

  ruecklagen: (id: string) =>
    client.get<{ ruecklagen: Ruecklage[]; blockiert: boolean; klaerungsfaelle: number }>(
      `${BASE}/${id}/ruecklagen/`).then(r => r.data),

  // Fixer Wirtschaftsplan-Wert der Rücklagenzuführung je BA (leer = löschen)
  ruecklagenPlanSpeichern: (id: string, baNr: string, betrag: string | null) =>
    client.patch<{ ok: boolean; ba_nr: string; betrag: string | null }>(
      `${BASE}/${id}/ruecklagen-plan/`, { ba_nr: baNr, betrag }).then(r => r.data),

  einzelabrechnungenBerechnen: (id: string) =>
    client.post<EinzelAbrechnung[]>(`${BASE}/${id}/einzelabrechnungen/berechnen/`).then(r => r.data),

  einzelabrechnungen: (id: string) =>
    client.get<EinzelAbrechnung[]>(`${BASE}/${id}/einzelabrechnungen/`).then(r => r.data),

  einzelabrechnungKorrigieren: (
    id: string, einheitId: string,
    positionen: EinzelAbrechnungPosition[], grund: string,
  ) =>
    client.patch<EinzelAbrechnung>(`${BASE}/${id}/einzelabrechnungen/${einheitId}/`, {
      positionen,
      grund,
    }).then(r => r.data),

  // PDF als Blob (Bearer-Token läuft über den axios-Client mit)
  pdfVorschau: (id: string, einheitId: string) =>
    client.get<Blob>(`${BASE}/${id}/pdf-vorschau/`, {
      params: { einheit: einheitId },
      responseType: 'blob',
    }).then(r => r.data),

  freigeben: (id: string) =>
    client.post<FreigabeResponse>(`${BASE}/${id}/freigeben/`).then(r => r.data),

  // Schritt 2: offene Kreditor-OPs per Saldovortrag ins Folgejahr schieben
  kreditorVortrag: (id: string, opNummern: number[]) =>
    client.post<KreditorVortragResponse>(
      `${BASE}/${id}/kreditor-vortrag/`, { op_nummern: opNummern }).then(r => r.data),
}
