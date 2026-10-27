import client from './client'
import type { Dokument, ObjektDokument } from '../types'

/** Ein aufgelöster Vorschlagstreffer (Objekt/Einheit/Person/Register). */
export interface VorschlagRef {
  id: string
  label: string
  /** Nur bei einer Einheit gesetzt: ID des übergeordneten Objekts. */
  objekt?: string
}

/** Antwort von POST /dokumente/upload-vorschlag/ — reine Vorschläge, nichts
 *  ist gesetzt. `owner` nennt das bevorzugte Kontextfeld (oder null). */
export interface UploadVorschlag {
  inhalt_erkannt: boolean
  kontext: {
    owner: 'objekt' | 'einheit' | 'person' | null
    objekt: VorschlagRef | null
    einheit: VorschlagRef | null
    person: VorschlagRef | null
    quelle: string
    konfidenz: number | null
    begruendung: string
    fehler: string
  }
  register: {
    register_id: string | null
    code: string
    bezeichnung: string
    aktenart: string
    quelle: string
    konfidenz: number | null
    begruendung: string
    fehler: string
  }
}

/** Felder beim bestätigten Upload. Genau EINES von objekt/einheit/person wird
 *  gesetzt (Owner-Regel des Dokument-Modells). */
export interface DokumentUploadFelder {
  objekt?: string | null
  einheit?: string | null
  person?: string | null
  register?: string | null
  kategorie: string
  dokument_typ?: string
  beschreibung?: string
}

export const dokumenteApi = {
  list: (params?: Record<string, string>) =>
    client.get<Dokument[]>('/dokumente/', { params }).then(r => r.data),
  get: (id: string) => client.get<Dokument>(`/dokumente/${id}/`).then(r => r.data),
  delete: (id: string) => client.delete(`/dokumente/${id}/`),

  /** Analysiert die Datei und schlägt Kontext + Register vor — ohne etwas
   *  anzulegen. Lazy aufrufen (die KI-Stufen kosten pro Aufruf). */
  analyseVorschlag: (file: File, beschreibung?: string, dokumentTyp?: string) => {
    const form = new FormData()
    form.append('datei', file)
    if (beschreibung) form.append('beschreibung', beschreibung)
    if (dokumentTyp) form.append('dokument_typ', dokumentTyp)
    return client.post<UploadVorschlag>('/dokumente/upload-vorschlag/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  upload: (file: File, felder: DokumentUploadFelder) => {
    const form = new FormData()
    form.append('datei', file)
    // dateiname ist ein eigenes Pflichtfeld des Dokuments (die Brücke zur Datei
    // im Archivordner) — aus dem Dateinamen der hochgeladenen Datei ableiten.
    form.append('dateiname', file.name)
    form.append('kategorie', felder.kategorie)
    // Genau einen Kontext-FK setzen — der Owner muss eindeutig sein.
    if (felder.einheit) form.append('einheit', felder.einheit)
    else if (felder.person) form.append('person', felder.person)
    else if (felder.objekt) form.append('objekt', felder.objekt)
    if (felder.register) form.append('register', felder.register)
    if (felder.dokument_typ) form.append('dokument_typ', felder.dokument_typ)
    if (felder.beschreibung) form.append('beschreibung', felder.beschreibung)
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
