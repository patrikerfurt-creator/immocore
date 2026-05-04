import client from './client'
import type { Kreditor, DublettKandidat, Rechnung, RechnungList, RechnungsMatchRegel } from '../types'

export const rechnungenApi = {
  // Kreditoren
  kreditoren: (params?: Record<string, string>) =>
    client.get<Kreditor[]>('/kreditoren/', { params }).then(r => r.data),
  getKreditor: (id: string) =>
    client.get<Kreditor>(`/kreditoren/${id}/`).then(r => r.data),
  createKreditor: (data: Partial<Kreditor>) =>
    client.post<Kreditor>('/kreditoren/', data).then(r => r.data),
  updateKreditor: (id: string, data: Partial<Kreditor>) =>
    client.patch<Kreditor>(`/kreditoren/${id}/`, data).then(r => r.data),
  deaktivierenKreditor: (id: string) =>
    client.post(`/kreditoren/${id}/deaktivieren/`).then(r => r.data),
  kreditorKontoauszug: (id: string, params?: Record<string, string>) =>
    client.get(`/kreditoren/${id}/kontoauszug/`, { params }).then(r => r.data),
  duplikatPruefen: (name: string, iban?: string) =>
    client.post<{ kandidaten: DublettKandidat[] }>('/kreditoren/duplikat-pruefen/', { name, iban }).then(r => r.data),

  // Rechnungen
  list: (params?: Record<string, string>) =>
    client.get<RechnungList[]>('/rechnungen/', { params }).then(r => r.data),
  get: (id: string) =>
    client.get<Rechnung>(`/rechnungen/${id}/`).then(r => r.data),
  create: (data: Partial<Rechnung>) =>
    client.post<Rechnung>('/rechnungen/', data).then(r => r.data),
  update: (id: string, data: Partial<Rechnung>) =>
    client.patch<Rechnung>(`/rechnungen/${id}/`, data).then(r => r.data),
  freigeben: (id: string, data?: { begruendung?: string; aufwandskonto_id?: string }) =>
    client.post(`/rechnungen/${id}/freigeben/`, data ?? {}).then(r => r.data),
  ablehnen: (id: string, begruendung: string) =>
    client.post(`/rechnungen/${id}/ablehnen/`, { begruendung }).then(r => r.data),
  alsNeu: (id: string) =>
    client.post(`/rechnungen/${id}/als-neu/`).then(r => r.data),
  buchen: (id: string, data: { objekt_id: string; konto_id: string }) =>
    client.post(`/rechnungen/${id}/buchen/`, data).then(r => r.data),
  bezahlen: (id: string, data?: { buchungsdatum?: string }) =>
    client.post(`/rechnungen/${id}/bezahlen/`, data ?? {}).then(r => r.data),
  bankabgang: (id: string, data: { haben_konto_id: string; buchungsdatum?: string }) =>
    client.post(`/rechnungen/${id}/bankabgang/`, data).then(r => r.data),
  openPdf: async (id: string) => {
    const response = await client.get(`/rechnungen/${id}/pdf/`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    window.open(url, '_blank')
  },
  logs: (id: string) =>
    client.get(`/rechnungen/${id}/logs/`).then(r => r.data),
  erkennungAusfuehren: (id: string) =>
    client.post<Rechnung>(`/rechnungen/${id}/erkennung-ausfuehren/`).then(r => r.data),
  erkennungsLog: (id: string) =>
    client.get(`/rechnungen/${id}/erkennungs-log/`).then(r => r.data),
  identifizieren: (id: string, data: {
    kreditor_id: string; objekt_id: string; aufwandskonto_id?: string
    modus?: 'speichern' | 'freigeben'; lernen?: boolean
  }) =>
    client.post<Rechnung>(`/rechnungen/${id}/identifizieren/`, data).then(r => r.data),
  manuellErfassen: (id: string, data: Record<string, unknown>) =>
    client.post<Rechnung>(`/rechnungen/${id}/manuell-erfassen/`, data).then(r => r.data),

  // Frontoffice Lock
  lockSetzen: (id: string) =>
    client.post(`/rechnungen/${id}/lock/`).then(r => r.data),
  lockLoesen: (id: string) =>
    client.delete(`/rechnungen/${id}/lock/`),
  lockHeartbeat: (id: string) =>
    client.post(`/rechnungen/${id}/lock/heartbeat/`).then(r => r.data),

  // Match-Regeln
  matchRegeln: (params?: Record<string, string>) =>
    client.get<RechnungsMatchRegel[]>('/match-regeln/', { params }).then(r => r.data),
  matchRegelDeaktivieren: (id: string) =>
    client.post<RechnungsMatchRegel>(`/match-regeln/${id}/deaktivieren/`).then(r => r.data),

  // Globale Freigabelimit-Defaults
  freigabelimitStandard: () =>
    client.get<{ grenzen: FreigabeLimit[] }>('/freigabelimits-standard/').then(r => r.data.grenzen),
  freigabelimitStandardSpeichern: (grenzen: FreigabeLimit[]) =>
    client.put<{ grenzen: FreigabeLimit[] }>('/freigabelimits-standard/', { grenzen }).then(r => r.data.grenzen),
}

export interface FreigabeLimit {
  bis: number | null
  rolle: string
  frist_tage: number
  beschreibung: string
}
