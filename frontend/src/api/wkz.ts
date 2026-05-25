/**
 * WKZ — Wiederkehrende Buchungen API
 */
import client from './client'

export interface WKZSplit {
  id: string
  kontonummer: string
  bezeichnung: string
  betrag: string
  reihenfolge: number
}

export interface WKZVorlage {
  id: string
  objekt: string
  objekt_bezeichnung: string
  kreditor: string
  kreditor_name: string
  bezeichnung: string
  typ: 'bescheid' | 'vertrag'
  status: 'entwurf' | 'eingereicht' | 'aktiv' | 'pausiert' | 'beendet'
  betrag_gesamt: string
  rhythmus: string
  erste_faelligkeit: string
  bei_wochenende: string
  vorlauf_tage: number
  toleranz_betrag: string
  toleranz_tage: number
  sepa_mandat_id: string
  bescheid_pflicht: boolean
  gueltig_ab: string
  gueltig_bis: string | null
  jahresbetrag: string | null
  perioden_pro_jahr: number | null
  freigegeben_am: string | null
  freigegeben_von_name: string | null
  freigabe_jahresbetrag: string | null
  ersetzt_vorlage_id: string | null
  erstellt_von_name: string
  erstellt_am: string
  geaendert_am: string
  splits: WKZSplit[]
}

export interface WKZVorlageCreate {
  objekt: string
  kreditor: string
  bezeichnung: string
  typ: 'bescheid' | 'vertrag'
  betrag_gesamt: string
  rhythmus: string
  erste_faelligkeit: string
  bei_wochenende?: string
  vorlauf_tage?: number
  toleranz_betrag?: string
  toleranz_tage?: number
  sepa_mandat_id?: string
  bescheid_pflicht?: boolean
  gueltig_ab: string
  gueltig_bis?: string | null
  splits: Array<{
    kontonummer: string
    bezeichnung: string
    betrag: string
    reihenfolge?: number
  }>
}

export interface WKZOP {
  id: string
  vorlage: string
  vorlage_bezeichnung: string
  kreditor_name: string
  op_nummer: number
  periode_von: string
  periode_bis: string
  faellig_am: string
  status: 'erzeugt' | 'bescheid_fehlt' | 'bankabgang_erfolgt' | 'abweichend_geklaert' | 'verworfen'
  erwarteter_betrag: string
  abweichung_betrag: string | null
  erzeugt_am: string
  klaerungs_grund?: string
  bank_match_buchung_id?: string
  splits?: WKZSplit[]
}

export interface WKZForecastPosition {
  faellig_am: string
  periode_von: string
  periode_bis: string
  kreditor: string
  bezeichnung: string
  betrag: string
  vorlage_id: string
}

export const wkzApi = {
  // Vorlagen je Objekt
  vorlagenJeObjekt: (objektId: string, params?: Record<string, string>) =>
    client
      .get<WKZVorlage[]>(`/objekte/${objektId}/wkz-vorlagen/`, { params })
      .then(r => r.data),

  // Vorlage anlegen
  vorlageAnlegen: (objektId: string, data: WKZVorlageCreate) =>
    client
      .post<WKZVorlage>(`/objekte/${objektId}/wkz-vorlagen/`, data)
      .then(r => r.data),

  // Vorlage-Detail
  vorlageDetail: (id: string) =>
    client.get<WKZVorlage>(`/wkz-vorlagen/${id}/`).then(r => r.data),

  // Vorlage bearbeiten (nur entwurf)
  vorlageBearbeiten: (id: string, data: Partial<WKZVorlageCreate>) =>
    client.patch<WKZVorlage>(`/wkz-vorlagen/${id}/`, data).then(r => r.data),

  // Lifecycle-Aktionen
  vorlageEinreichen: (id: string) =>
    client.post<WKZVorlage>(`/wkz-vorlagen/${id}/einreichen/`).then(r => r.data),

  vorlageFreigeben: (id: string) =>
    client.post<WKZVorlage>(`/wkz-vorlagen/${id}/freigeben/`).then(r => r.data),

  vorlagePausieren: (id: string, grund: string) =>
    client.post<WKZVorlage>(`/wkz-vorlagen/${id}/pausieren/`, { grund }).then(r => r.data),

  vorlageReaktivieren: (id: string) =>
    client.post<WKZVorlage>(`/wkz-vorlagen/${id}/reaktivieren/`).then(r => r.data),

  vorlageBeenden: (id: string, gueltig_bis: string, grund: string) =>
    client
      .post<WKZVorlage>(`/wkz-vorlagen/${id}/beenden/`, { gueltig_bis, grund })
      .then(r => r.data),

  vorlageErsetzen: (id: string, neue_daten: Record<string, unknown>, splits: WKZVorlageCreate['splits']) =>
    client
      .post<WKZVorlage>(`/wkz-vorlagen/${id}/ersetzen/`, { neue_daten, splits })
      .then(r => r.data),

  // Forecast dieser Vorlage (nächste 12 Fälligkeiten)
  vorlageForecast: (id: string) =>
    client
      .get<Array<{ faellig_am: string; periode_von: string; periode_bis: string; betrag: string }>>(
        `/wkz-vorlagen/${id}/forecast/`
      )
      .then(r => r.data),

  // Objekt-Liquiditätsforecast 90 Tage
  objektForecast: (objektId: string) =>
    client
      .get<WKZForecastPosition[]>(`/objekte/${objektId}/wkz-forecast/`)
      .then(r => r.data),

  // WKZ-OP-Detail
  opDetail: (id: string) =>
    client.get<WKZOP>(`/wkz-ops/${id}/`).then(r => r.data),

  // WKZ-OPs je Vorlage
  opsJeVorlage: (vorlageId: string, params?: Record<string, string>) =>
    client.get<WKZOP[]>('/wkz-ops/', { params: { vorlage: vorlageId, ...params } }).then(r => r.data),

  // OP verwerfen
  opVerwerfen: (id: string, grund: string) =>
    client.post<WKZOP>(`/wkz-ops/${id}/verwerfen/`, { grund }).then(r => r.data),

  // OP manuell verbuchen
  opManuellVerbuchen: (id: string, kontoumsatzId: string, splitsOverride?: Record<string, string>) =>
    client
      .post(`/wkz-ops/${id}/manuell-verbuchen/`, {
        kontoumsatz_id: kontoumsatzId,
        splits_override: splitsOverride,
      })
      .then(r => r.data),

  // Alle Vorlagen eines Kreditors
  vorlagenJeKreditor: (kreditorId: string, params?: Record<string, string>) =>
    client
      .get<WKZVorlage[]>(`/kreditoren/${kreditorId}/wkz-vorlagen/`, { params })
      .then(r => r.data),
}
