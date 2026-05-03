import client from './client'
import type { Objekt, ObjektList, Einheit, Bankkonto, Verteilerschluessel, VerteilerschluesselWert } from '../types'

export const objekteApi = {
  list: () => client.get<ObjektList[]>('/objekte/').then(r => r.data),
  get: (id: string) => client.get<Objekt>(`/objekte/${id}/`).then(r => r.data),
  create: (data: Partial<Objekt>) => client.post<Objekt>('/objekte/', data).then(r => r.data),
  update: (id: string, data: Partial<Objekt>) => client.patch<Objekt>(`/objekte/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/objekte/${id}/`),

  // Einheiten
  listEinheiten: (params?: Record<string, string>) =>
    client.get<Einheit[]>('/einheiten/', { params }).then(r => r.data),
  createEinheit: (data: Partial<Einheit>) => client.post<Einheit>('/einheiten/', data).then(r => r.data),
  updateEinheit: (id: string, data: Partial<Einheit>) => client.patch<Einheit>(`/einheiten/${id}/`, data).then(r => r.data),
  deleteEinheit: (id: string) => client.delete(`/einheiten/${id}/`),
  csvVorlageEinheiten: (objektId?: string) =>
    client.get('/einheiten/csv-vorlage/', {
      params: objektId ? { objekt: objektId } : {},
      responseType: 'blob',
    }).then(r => r.data as Blob),
  csvVorschauEinheiten: (file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<{
      rows: Array<{ zeile: number; status: string; fehler: string[]; daten: Record<string, string | null> }>
      ok_anzahl: number
      fehler_anzahl: number
      gesamt: number
    }>('/einheiten/csv-vorschau/', fd, { headers: { 'Content-Type': undefined } }).then(r => r.data)
  },
  csvImportEinheiten: (rows: Array<Record<string, unknown>>) =>
    client.post<{ angelegt: number; fehler: string[] }>(
      '/einheiten/csv-import/', { rows }
    ).then(r => r.data),

  // Bankkonten
  createBankkonto: (data: Partial<Bankkonto>) => client.post<Bankkonto>('/bankkonten/', data).then(r => r.data),
  updateBankkonto: (id: string, data: Partial<Bankkonto>) => client.patch<Bankkonto>(`/bankkonten/${id}/`, data).then(r => r.data),
  deleteBankkonto: (id: string) => client.delete(`/bankkonten/${id}/`),

  // Verteilerschlüssel (Flächen / MEA)
  verteilerschluessel: (params?: Record<string, string>) =>
    client.get<Verteilerschluessel[]>('/verteilerschluessel/', { params }).then(r => r.data),
  wertSetzen: (schluesselId: string, einheitId: string, wert: string) =>
    client.post<VerteilerschluesselWert>(
      `/verteilerschluessel/${schluesselId}/wert-setzen/`,
      { einheit: einheitId, wert }
    ).then(r => r.data),
  deleteWert: (wertId: string) =>
    client.delete(`/verteilerschluessel-werte/${wertId}/`),
}
