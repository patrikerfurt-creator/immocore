import client from './client'

export interface WirtschaftsplanList {
  id: string
  wirtschaftsjahr: string
  wirtschaftsjahr_jahr: number
  objekt_id: string
  objekt_bezeichnung: string
  status: 'entwurf' | 'beschlossen' | 'aktiv' | 'aufgehoben'
  gesamtsumme: string
  gesamtsumme_hausgeld: string
  gesamtsumme_ruecklage: Record<string, number>
  beschluss_datum: string | null
  beschluss_tagesordnungspunkt: string | null
  wirkung_ab: string
  bemerkung: string | null
  aufhebt_wp: string | null
  erstellt_am: string
  erstellt_von: number
  erstellt_von_name: string
  beschlossen_am: string | null
}

export interface WirtschaftsplanAnteil {
  id: string
  einheit: string
  einheit_nr: string
  einheit_lage: string
  vs_anteil_einheit: string
  vs_anteil_gesamt: string
  betrag_anteil: string
  monatsbetrag_anteil: string
}

export interface WirtschaftsplanPosition {
  id: string
  konto: string
  konto_nr: string
  konto_name: string
  konto_kontoart: string
  vs_code: string
  betrag: string
  verteilung_validiert: boolean
  verteilung_freigegeben_trotz_diff: boolean
  bemerkung: string | null
  anteile: WirtschaftsplanAnteil[]
  summe_anteile: number
  differenz: number
}

export interface WirtschaftsplanDetail extends WirtschaftsplanList {
  positionen: WirtschaftsplanPosition[]
}

export interface WpKonto {
  id: string
  kontonummer: string
  kontoname: string
  kontoart: string
  abrechnungsart: string | null
  vs_code: string | null
  hat_vs: boolean
  position_id: string | null
  betrag: string
  verteilung_validiert: boolean
  verteilung_freigegeben_trotz_diff: boolean
}

export interface VorschauZeile {
  ev_id: string
  einheit_nr: string
  lage: string
  person_name: string
  ba_betraege: Record<string, number>
  summe: number
  delta: number
}

export const wirtschaftsplanApi = {
  list: (params?: Record<string, string>) =>
    client.get<WirtschaftsplanList[]>('/wirtschaftsplaene/', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<WirtschaftsplanDetail>(`/wirtschaftsplaene/${id}/`).then(r => r.data),

  create: (data: { wirtschaftsjahr_id: string; wirkung_ab: string }) =>
    client.post<WirtschaftsplanDetail>('/wirtschaftsplaene/', data).then(r => r.data),

  konten: (id: string) =>
    client.get<WpKonto[]>(`/wirtschaftsplaene/${id}/konten/`).then(r => r.data),

  positionUpsert: (id: string, data: { konto_id: string; betrag: string }) =>
    client.post<WirtschaftsplanPosition>(`/wirtschaftsplaene/${id}/positionen/`, data).then(r => r.data),

  positionLoeschen: (id: string, kontoId: string) =>
    client.delete(`/wirtschaftsplaene/${id}/positionen/${kontoId}/`),

  freigabeTrotzDiff: (id: string, kontoId: string) =>
    client.post(`/wirtschaftsplaene/${id}/freigabe-trotz-diff/`, { konto_id: kontoId }).then(r => r.data),

  vorschauHausgeld: (id: string) =>
    client.get<{ vorschau: VorschauZeile[] }>(`/wirtschaftsplaene/${id}/vorschau-hausgeld/`).then(r => r.data),

  beschluss: (id: string, data: { beschluss_datum: string; top?: string; bemerkung?: string }) =>
    client.post<{ wp: WirtschaftsplanDetail; stats: Record<string, unknown> }>(
      `/wirtschaftsplaene/${id}/beschluss/`, data
    ).then(r => r.data),

  korrekturbeschluss: (id: string) =>
    client.post<WirtschaftsplanDetail>(`/wirtschaftsplaene/${id}/korrekturbeschluss/`).then(r => r.data),

  pdfGesamt: (id: string) =>
    client.get(`/wirtschaftsplaene/${id}/pdf/gesamt/`, { responseType: 'blob' }).then(r => r.data as Blob),

  pdfEinzeln: (id: string, params: { einheit_id?: string; bulk?: boolean }) =>
    client.get(`/wirtschaftsplaene/${id}/pdf/einzeln/`, {
      params: {
        ...(params.einheit_id ? { einheit_id: params.einheit_id } : {}),
        ...(params.bulk ? { bulk: '1' } : {}),
      },
      responseType: 'blob',
    }).then(r => r.data as Blob),
}
