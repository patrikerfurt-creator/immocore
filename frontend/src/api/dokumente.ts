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

  /**
   * Lesbare Textvorschau einer abgelegten Mail (.eml/.msg).
   *
   * Der Umweg über den Blob ist nötig, weil der Endpunkt Authentifizierung
   * verlangt — ein einfaches window.open() würde ohne Token 401 liefern.
   * Der Schutz vor Schadcode aus der Mail liegt deshalb im Backend, das
   * jeden Wert HTML-escaped ausgibt: die CSP-Header der Antwort greifen
   * bei einer blob:-URL nicht mehr.
   */
  /**
   * Liefert die Vorschau als HTML-Text — fuer die Einbettung per
   * <iframe srcDoc sandbox="">.
   *
   * Bewusst NICHT als blob:-URL: ein iframe mit sandbox="" bekommt einen
   * opaken Origin und kann eine blob:-URL des App-Origins gar nicht laden,
   * das Fenster bliebe leer. Mit srcDoc entfaellt die URL-Aufloesung, die
   * vollstaendige Isolation bleibt erhalten — und es gibt nichts
   * freizugeben.
   */
  mailVorschauHtml: async (id: string, kompakt = false): Promise<string> => {
    const response = await client.get(`/dokumente/${id}/mail-vorschau/`, {
      responseType: 'text',
      params: kompakt ? { kompakt: 1 } : undefined,
      // Ohne das versucht axios, die Antwort als JSON zu parsen.
      transformResponse: [(daten) => daten],
    })
    return response.data as string
  },

  openMailVorschau: async (id: string) => {
    const response = await client.get(`/dokumente/${id}/mail-vorschau/`, {
      responseType: 'blob',
    })
    const blob = new Blob([response.data], { type: 'text/html; charset=utf-8' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  },
}
