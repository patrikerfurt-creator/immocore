import client from './client'

export interface Wirtschaftsplan {
  id: string
  wirtschaftsjahr: string
  wj_jahr: number
  objekt_id: string
  objekt_bezeichnung: string
  status: 'entwurf' | 'beschlossen' | 'aktiv' | 'aufgehoben'
  gesamtsumme: string
  gesamtsumme_hausgeld: string
  gesamtsumme_ruecklage: Record<string, string>
  beschluss_datum: string | null
  beschluss_tagesordnungspunkt: string | null
  wirkung_ab: string
  bemerkung: string | null
  aufhebt_wp: string | null
  erstellt_am: string
  erstellt_von: number
  erstellt_von_name: string
  anzahl_positionen?: number
  positionen?: WirtschaftsplanPosition[]
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
  wirtschaftsplan: string
  konto: string
  kontonummer: string
  kontoname: string
  abrechnungsart: string | null
  vs_code: string
  betrag: string
  verteilung_validiert: boolean
  verteilung_freigegeben_trotz_diff: boolean
  bemerkung: string | null
  anteile: WirtschaftsplanAnteil[]
  anteile_summe: string
  differenz: string
}

export interface VerfuegbaresKonto {
  id: string
  kontonummer: string
  kontoname: string
  kontoart: string
  abrechnungsart: string | null
  vs_code: string | null
  hat_vs: boolean
  hat_position: boolean
}

export interface VorschauPosition {
  ev_id: string
  einheit_nr: string
  lage: string
  person_name: string
  bas: Record<string, string>
  summe: string
}

export const wirtschaftsplanApi = {
  list: (params?: { objekt?: string; wirtschaftsjahr?: string; status?: string }) =>
    client.get<Wirtschaftsplan[]>('/wirtschaftsplaene/', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Wirtschaftsplan>(`/wirtschaftsplaene/${id}/`).then(r => r.data),

  create: (data: { wirtschaftsjahr: string; wirkung_ab: string; bemerkung?: string }) =>
    client.post<Wirtschaftsplan>('/wirtschaftsplaene/', data).then(r => r.data),

  update: (id: string, data: Partial<Wirtschaftsplan>) =>
    client.patch<Wirtschaftsplan>(`/wirtschaftsplaene/${id}/`, data).then(r => r.data),

  upsertPosition: (wpId: string, konto: string, betrag: string) =>
    client.post<WirtschaftsplanPosition>(`/wirtschaftsplaene/${wpId}/positionen/`, { konto, betrag }).then(r => r.data),

  deletePosition: (wpId: string, posId: string) =>
    client.delete(`/wirtschaftsplaene/${wpId}/positionen/${posId}/`).then(r => r.data),

  freigabeTrotzDiff: (wpId: string, posId: string) =>
    client.post<WirtschaftsplanPosition>(`/wirtschaftsplaene/${wpId}/positionen/${posId}/freigabe-trotz-diff/`).then(r => r.data),

  vorschauHausgeld: (wpId: string) =>
    client.get<{ positionen: VorschauPosition[]; wp_id: string }>(`/wirtschaftsplaene/${wpId}/vorschau-hausgeld/`).then(r => r.data),

  beschluss: (wpId: string, data: { beschluss_datum: string; top?: string; bemerkung?: string }) =>
    client.post<{ status: string; nachhol_sollstellungs_ids: string[] }>(`/wirtschaftsplaene/${wpId}/beschluss/`, data).then(r => r.data),

  korrekturbeschluss: (wpId: string) =>
    client.post<Wirtschaftsplan>(`/wirtschaftsplaene/${wpId}/korrekturbeschluss/`).then(r => r.data),

  verfuegbareKonten: (wpId: string) =>
    client.get<VerfuegbaresKonto[]>(`/wirtschaftsplaene/${wpId}/verfuegbare-konten/`).then(r => r.data),
}
