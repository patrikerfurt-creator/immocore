import client from './client'
import type { Dokument, ObjektDokument } from '../types'

export const dokumenteApi = {
  list: (params?: Record<string, string>) =>
    client.get<Dokument[]>('/dokumente/', { params }).then(r => r.data),
  get: (id: string) => client.get<Dokument>(`/dokumente/${id}/`).then(r => r.data),
  delete: (id: string) => client.delete(`/dokumente/${id}/`),

  upload: (objektId: string, file: File, kategorie: string, beschreibung?: string) => {
    const form = new FormData()
    form.append('objekt', objektId)
    form.append('datei', file)
    form.append('kategorie', kategorie)
    if (beschreibung) form.append('beschreibung', beschreibung)
    return client.post<Dokument>('/dokumente/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  // Minimaler DMS-Lesezugriff (Spec Beleg↔Dokument-Kopplung, Abschnitt 7)
  listByObjekt: (objektId: string, typ?: string) =>
    client.get<ObjektDokument[]>(`/objekte/${objektId}/dokumente/`, {
      params: typ ? { typ } : undefined,
    }).then(r => r.data),

  openDatei: async (id: string) => {
    const response = await client.get(`/dokumente/${id}/datei/`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    window.open(url, '_blank')
  },
}
