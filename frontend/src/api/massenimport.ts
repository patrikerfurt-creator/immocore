import client from './client'

export interface ZeileVorschau {
  zeilennummer: number
  status: 'ok' | 'warnung' | 'fehler'
  meldungen: string[]
  bezeichnung: string
  eingaenge_anzahl: number
  ruecklagen: number
  konten_anzahl: number
  abrechnungsarten_anzahl: number
}

export interface PreviewSummary {
  ok: number
  warnung: number
  fehler: number
  gesamt: number
  objekte: number
  liegenschaften: number
  bankkonten: number
  konten: number
  abrechnungsarten: number
}

export interface PreviewResponse {
  job_id: string
  preview_token: string
  zeilen: ZeileVorschau[]
  summary: PreviewSummary
}

export interface CommitErgebnis {
  zeilennummer: number
  status: 'ok' | 'fehler' | 'uebersprungen'
  objekt_id?: string
  bezeichnung?: string
  meldung?: string
}

export interface CommitResponse {
  job_id: string
  status: 'committed' | 'partial' | 'failed'
  importiert: number
  fehler: number
  ergebnisse: CommitErgebnis[]
}

export const massenimportApi = {
  vorlageHerunterladen: () =>
    client.get('/massenimport/vorlage/weg/', { responseType: 'blob' }).then(r => r.data as Blob),

  preview: (datei: File) => {
    const form = new FormData()
    form.append('datei', datei)
    return client
      .post<PreviewResponse>('/massenimport/weg/preview/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(r => r.data)
  },

  commit: (previewToken: string) =>
    client.post<CommitResponse>('/massenimport/weg/commit/', { preview_token: previewToken }).then(r => r.data),

  jobStatus: (jobId: string) =>
    client.get(`/massenimport/jobs/${jobId}/`).then(r => r.data),
}
