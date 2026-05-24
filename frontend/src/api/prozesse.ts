import client from './client'
import type { Prozess, ProzessTyp, WechselAnalyse } from '../types'

export const prozesseApi = {
  list: (params?: Record<string, string>) =>
    client.get<Prozess[]>('/prozesse/', { params }).then(r => r.data),
  get: (id: string) => client.get<Prozess>(`/prozesse/${id}/`).then(r => r.data),

  starten: (prozess_typ: ProzessTyp, objekt?: string) =>
    client.post<Prozess>('/prozesse/', { prozess_typ, objekt }).then(r => r.data),

  schritte: (id: string) =>
    client.get(`/prozesse/${id}/schritte/`).then(r => r.data),

  schrittSpeichern: (id: string, schritt: number, data: Record<string, unknown>) =>
    client.post(`/prozesse/${id}/schritt-speichern/`, { schritt, data }).then(r => r.data),

  abbrechen: (id: string) =>
    client.post(`/prozesse/${id}/abbrechen/`).then(r => r.data),

  // Step definition + saved data
  getStep: (id: string, nr: number) =>
    client.get(`/prozesse/${id}/step/${nr}/`).then(r => r.data),

  // Save step data (PATCH)
  saveStep: (id: string, nr: number, daten: Record<string, unknown>) =>
    client.patch(`/prozesse/${id}/step/${nr}/`, { daten }).then(r => r.data),

  // CSV templates
  csvVorlageEinheiten: (id: string) =>
    client.get(`/prozesse/${id}/csv-vorlage/einheiten/`, { responseType: 'blob' }).then(r => r.data),
  csvVorlageEigentuemer: (id: string) =>
    client.get(`/prozesse/${id}/csv-vorlage/eigentuemer/`, { responseType: 'blob' }).then(r => r.data),

  // CSV upload
  csvUploadEinheiten: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client.post(`/prozesse/${id}/csv-upload/einheiten/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  csvUploadEigentuemer: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client.post(`/prozesse/${id}/csv-upload/eigentuemer/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  // Atomic activation (step 10)
  abschliessen: (id: string) =>
    client.post(`/prozesse/${id}/abschliessen/`).then(r => r.data),

  // Eigentümerwechsel: read-only analysis of seller's Sollstellungen
  ewAnalyse: (id: string) =>
    client.get<WechselAnalyse>(`/prozesse/${id}/ew-analyse/`).then(r => r.data),
}
