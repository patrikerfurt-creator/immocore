import client from './client'
import type { Person, PersonList, EigentumsVerhaeltnis, SEPAMandat } from '../types'

export interface CsvVorschauRow {
  zeile: number
  csv_data: {
    person_typ: string
    ist_firma: boolean
    anrede: string
    firmenname: string
    vorname: string
    nachname: string
    email: string
    adresse: string
    iban: string
  }
  status: 'neu' | 'duplikat' | 'fehler'
  fehler: string[]
  duplikat: {
    id: string | null
    personennummer: string | null
    name: string
    email: string
    adresse: string
    grund: string
    quelle: 'datei' | 'datenbank'
    zeile_ref: number | null
  } | null
  aktion: 'importieren' | 'ablehnen'
}

export interface CsvVorschauResponse {
  rows: CsvVorschauRow[]
  errors: string[]
}

export interface CsvImportResponse {
  importiert: number
  abgelehnt: number
  errors: string[]
}

export interface VertraegeVorschauZeile {
  zeile: number
  fl_nr: string
  personnummer: string
  et_ab: string
  sollarten: { kontoart: string; betrag: number | null; betrag_raw: string; gueltig_ab: string }[]
  status: 'ok' | 'warnung' | 'fehler'
  fehler: string[]
  info: string[]
  einheit_info: { id: string; einheit_nr: string; lage: string } | null
  person_info: { id: string; name: string } | null
  ev_aktion: 'neu' | 'aktualisieren' | 'ersetzen' | null
}

export interface VertraegeVorschauResponse {
  rows: VertraegeVorschauZeile[]
  ok_count: number
  fehler_count: number
}

export const personenApi = {
  list: (params?: Record<string, string>) =>
    client.get<PersonList[]>('/personen/', { params }).then(r => r.data),
  get: (id: string) => client.get<Person>(`/personen/${id}/`).then(r => r.data),
  create: (data: Partial<Person>) => client.post<Person>('/personen/', data).then(r => r.data),
  update: (id: string, data: Partial<Person>) => client.patch<Person>(`/personen/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/personen/${id}/`),

  csvVorlage: () =>
    client.get('/personen/csv-vorlage/', { responseType: 'blob' }).then(r => r.data as Blob),
  csvVorschau: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post<CsvVorschauResponse>('/personen/csv-vorschau/', fd, {
      headers: { 'Content-Type': undefined },
    }).then(r => r.data)
  },
  csvImport: (rows: Array<{ zeile: number; csv_data: CsvVorschauRow['csv_data']; aktion: string }>) =>
    client.post<CsvImportResponse>('/personen/csv-import/', { rows }).then(r => r.data),

  // Eigentumsverhältnisse
  eigentumsverhaeltnisse: (params?: Record<string, string>) =>
    client.get<EigentumsVerhaeltnis[]>('/eigentumsverhaeltnisse/', { params }).then(r => r.data),
  createEigentumsverhaeltnis: (data: Partial<EigentumsVerhaeltnis>) =>
    client.post<EigentumsVerhaeltnis>('/eigentumsverhaeltnisse/', data).then(r => r.data),

  // Hausgeld-Historie
  createHausgeldHistorie: (data: {
    eigentumsverhaeltnis: string
    betrag: string
    gueltig_ab: string
    kontoart: string
  }) => client.post('/hausgeld-historie/', data).then(r => r.data),

  // Verträge CSV
  vertraegeVorschau: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post<VertraegeVorschauResponse>(
      '/eigentumsverhaeltnisse/vertraege-vorschau/', fd,
      { params: { objekt: objektId }, headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  vertraegeVorlage: (objektId: string) =>
    client.get('/eigentumsverhaeltnisse/vertraege-vorlage/', {
      params: { objekt: objektId },
      responseType: 'blob',
    }).then(r => {
      const cd: string = r.headers['content-disposition'] ?? ''
      const match = cd.match(/filename="([^"]+)"/)
      return { blob: r.data as Blob, filename: match?.[1] ?? 'Vertraege.csv' }
    }),

  vertraegeImport: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post<{ importiert: number; personenkonten_angelegt: number; fehler: string[] }>(
      '/eigentumsverhaeltnisse/vertraege-import/', fd,
      { params: { objekt: objektId }, headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  // SEPA-Mandate
  createSepaMandat: (data: Omit<SEPAMandat, 'id'>) =>
    client.post<SEPAMandat>('/sepa-mandate/', data).then(r => r.data),
  updateSepaMandat: (id: string, data: Partial<SEPAMandat>) =>
    client.patch<SEPAMandat>(`/sepa-mandate/${id}/`, data).then(r => r.data),
  linkSepaMandat: (personId: string, mandatId: string | null) =>
    client.patch<Person>(`/personen/${personId}/`, { sepa_mandat: mandatId }).then(r => r.data),
}
