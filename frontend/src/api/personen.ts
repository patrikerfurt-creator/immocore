import client from './client'
import type { Person, PersonList, EigentumsVerhaeltnis, HausgeldHistorie, SEPAMandat } from '../types'

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

export interface CsvImportAktion {
  aktion: 'importieren' | 'ablehnen'
  preview_status: CsvVorschauRow['status']
  duplikat_personennummer: string | null
  duplikat_grund: string | null
  fehler_meldungen: string[]
}

export interface VertraegeZeilenErgebnis {
  zeilennummer: number
  einheit_nr: string
  abrechnungsart: string
  gueltig_ab: string
  betrag: string
  wirtschaftsplan_jahr: number | null
  aktion: 'neu' | 'aktualisiert' | 'bestehend_unveraendert' | 'vertrag_neu' | 'fehler'
  status: 'ok' | 'warnung' | 'fehler'
  meldungen: string[]
  historie_id: string | null
}

export interface VertraegePreviewResponse {
  objekt: { id: string; bezeichnung: string; objekt_nr: string }
  zusammenfassung: {
    zeilen_gesamt: number
    zeilen_ok: number
    zeilen_warnung: number
    zeilen_fehler: number
  }
  zeilen: VertraegeZeilenErgebnis[]
}

export type VertraegeVorschauResponse = VertraegePreviewResponse

export interface VertraegeCommitResponse {
  status: 'ok' | 'fehler'
  zusammenfassung: {
    zeilen_gesamt: number
    zeilen_ok: number
    zeilen_fehler: number
    vertraege_neu: number
    vertraege_bestehend: number
    historie_eintraege_neu: number
    historie_eintraege_aktualisiert: number
  }
  zeilen: VertraegeZeilenErgebnis[]
}

export const personenApi = {
  list: (params?: Record<string, string>) =>
    client.get<PersonList[]>('/personen/', { params }).then(r => r.data),
  get: (id: string) => client.get<Person>(`/personen/${id}/`).then(r => r.data),
  create: (data: Record<string, unknown>) => client.post<Person>('/personen/', data).then(r => r.data),
  update: (id: string, data: Record<string, unknown>) => client.patch<Person>(`/personen/${id}/`, data).then(r => r.data),
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
  csvImport: (csvDatei: File, aktionen: Record<number, CsvImportAktion>) => {
    const fd = new FormData()
    fd.append('csv_datei', csvDatei)
    fd.append('aktionen', JSON.stringify(aktionen))
    return client.post('/personen/csv-import/', fd, {
      headers: { 'Content-Type': undefined },
      responseType: 'blob',
    }).then(r => ({
      blob: r.data as Blob,
      filename: (r.headers['content-disposition'] as string ?? '')
        .match(/filename="([^"]+)"/)?.[1]
        ?? `${csvDatei.name.replace(/\.csv$/i, '')}_ergebnis.csv`,
    }))
  },

  // Eigentumsverhältnisse
  eigentumsverhaeltnisse: (params?: Record<string, string>) =>
    client.get<EigentumsVerhaeltnis[]>('/eigentumsverhaeltnisse/', { params }).then(r => r.data),
  createEigentumsverhaeltnis: (data: Partial<EigentumsVerhaeltnis>) =>
    client.post<EigentumsVerhaeltnis>('/eigentumsverhaeltnisse/', data).then(r => r.data),

  // Hausgeld-Historie
  createHausgeldHistorie: (data: {
    eigentumsverhaeltnis: string
    abrechnungsart: string
    betrag: string
    gueltig_ab: string
    wirtschaftsplan_jahr?: number | null
    quelle?: string
    bemerkung?: string
  }) => client.post('/hausgeld-historie/', data).then(r => r.data),

  hausgeldAktuell: (vertragId: string, stichtag?: string) =>
    client.get<Record<string, string>>(`/eigentumsverhaeltnisse/${vertragId}/hausgeld-aktuell/`, {
      params: stichtag ? { stichtag } : undefined,
    }).then(r => r.data),

  hausgeldHistorie: (vertragId: string) =>
    client.get(`/eigentumsverhaeltnisse/${vertragId}/hausgeld-historie/`).then(r => r.data),

  // Verträge CSV (neue Endpunkte auf /objekte/{id}/vertraege/...)
  vertraegeVorlage: (objektId: string) =>
    client.get(`/objekte/${objektId}/vertraege/csv-vorlage/`, { responseType: 'blob' }).then(r => {
      const cd: string = r.headers['content-disposition'] ?? ''
      const match = cd.match(/filename="([^"]+)"/)
      return { blob: r.data as Blob, filename: match?.[1] ?? 'Vertraege.csv' }
    }),

  vertraegePreview: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<VertraegePreviewResponse>(
      `/objekte/${objektId}/vertraege/csv-preview/`, fd,
      { headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  vertraegeVorschau: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<VertraegePreviewResponse>(
      `/objekte/${objektId}/vertraege/csv-preview/`, fd,
      { headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  vertraegeCommit: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<VertraegeCommitResponse>(
      `/objekte/${objektId}/vertraege/csv-commit/`, fd,
      { headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  vertraegeImport: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<VertraegeCommitResponse>(
      `/objekte/${objektId}/vertraege/csv-commit/`, fd,
      { headers: { 'Content-Type': undefined } },
    ).then(r => {
      const d = r.data
      return {
        importiert: d.zusammenfassung.historie_eintraege_neu + d.zusammenfassung.historie_eintraege_aktualisiert,
        personenkonten_angelegt: d.zusammenfassung.vertraege_neu,
        fehler: d.zeilen
          .filter(z => z.status === 'fehler')
          .flatMap(z => z.meldungen.map(m => `Zeile ${z.zeilennummer}: ${m}`)),
      }
    })
  },

  hausgeldEintraege: (evId: string) =>
    client.get<HausgeldHistorie[]>('/hausgeld-historie/', { params: { eigentumsverhaeltnis: evId } }).then(r => r.data),

  // SEPA-Mandate
  createSepaMandat: (data: Omit<SEPAMandat, 'id'>) =>
    client.post<SEPAMandat>('/sepa-mandate/', data).then(r => r.data),
  updateSepaMandat: (id: string, data: Partial<SEPAMandat>) =>
    client.patch<SEPAMandat>(`/sepa-mandate/${id}/`, data).then(r => r.data),
  linkSepaMandat: (personId: string, mandatId: string | null) =>
    client.patch<Person>(`/personen/${personId}/`, { sepa_mandat: mandatId }).then(r => r.data),
}
