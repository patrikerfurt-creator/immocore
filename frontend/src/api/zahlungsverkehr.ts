import client from './client'
import type { LastschriftLauf, HausgeldSollstellungslauf } from '../types'

export const zahlungsverkehrApi = {
  // Lastschrift-Läufe
  lastschriftLaeufe: (params?: Record<string, string>) =>
    client.get<LastschriftLauf[]>('/lastschrift-laeufe/', { params }).then(r => r.data),

  createLastschriftLauf: (data: {
    objekt_id: string
    hg_lauf_id?: string
    faelligkeitsdatum: string
    bezeichnung?: string
  }) =>
    client.post<LastschriftLauf>('/lastschrift-laeufe/', data).then(r => r.data),

  patchLastschriftLauf: (id: string, data: Partial<LastschriftLauf>) =>
    client.patch<LastschriftLauf>(`/lastschrift-laeufe/${id}/`, data).then(r => r.data),

  downloadLastschriftXml: async (id: string, dateiname: string) => {
    const response = await client.get(`/lastschrift-laeufe/${id}/xml/`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const a = document.createElement('a')
    a.href = url
    a.download = dateiname
    a.click()
    URL.revokeObjectURL(url)
  },

  // Hausgeld-Läufe für Lastschrift-Auswahl (nur commited)
  hausgeldLaeufe: (params?: Record<string, string>) =>
    client.get<HausgeldSollstellungslauf[]>('/hg-laeufe/', { params }).then(r => r.data),

  // SEPA Ausgangsüberweisungen (pain.001)
  exportRechnungenSepa: async (data: {
    rechnung_ids: string[]
    faelligkeitsdatum: string
  }) => {
    const response = await client.post('/rechnungen/sepa-export/', data, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `zahlungen_${data.faelligkeitsdatum.replace(/-/g, '')}.xml`
    a.click()
    URL.revokeObjectURL(url)
  },
}
