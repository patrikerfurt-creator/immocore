import client from './client'

/**
 * Akten: Haus-, Wohnungs- und Eigentümerakte.
 *
 * Die Akte kommt als FLACHE Liste von Registergruppen, jede mit `ebene` —
 * die Reihenfolge ist im Backend bereits als Baum gelegt (Unterregister
 * direkt hinter ihrem Elternregister). Die Oberfläche muss nur einrücken,
 * nicht selbst sortieren oder verschachteln.
 */

export interface AktenDokument {
  id: string
  /** Originalname der Datei — bleibt unangetastet (Bruecke zum Archiv). */
  dateiname: string
  /** Sprechender Name, falls gesetzt. */
  titel: string
  /** Was angezeigt wird: titel, sonst aus der Rechnung abgeleitet, sonst dateiname. */
  anzeigename: string
  dokument_typ: string
  kategorie: string
  beschreibung: string
  dokument_datum: string | null
  hochgeladen_am: string
  version: number
  ist_mail: boolean
  /** Über welchen Weg das Dokument in dieser Akte landet: "Einheit W01",
   *  "Vorgang V-26-00038", "Rechnungsbeleg", "Mail-Import", "Objekt". */
  herkunft: string
}

export interface RegisterGruppe {
  /** null bei der Sammelgruppe "Ohne Register". */
  register_id: string | null
  code: string
  bezeichnung: string
  pfad: string
  ebene: number
  objektspezifisch: boolean
  anzahl: number
  hinweis: string
  dokumente: AktenDokument[]
}

export interface Akte {
  titel: string
  aktenart: 'haus' | 'wohnung' | 'eigentuemer'
  anzahl_dokumente: number
  register: RegisterGruppe[]
  objekt?: string
  einheit?: string
  person?: string
}

export interface UnterregisterEingabe {
  code: string
  bezeichnung: string
  aktenart: string
  eltern: string
  objekt: string
  sortierung?: number
  hinweis?: string
}

export const aktenApi = {
  hausakte: (objektId: string): Promise<Akte> =>
    client.get('/akten/hausakte/', { params: { objekt: objektId } })
      .then(r => r.data),

  wohnungsakte: (einheitId: string): Promise<Akte> =>
    client.get('/akten/wohnungsakte/', { params: { einheit: einheitId } })
      .then(r => r.data),

  eigentuemerakte: (personId: string, nurAktuelle = false): Promise<Akte> =>
    client.get('/akten/eigentuemerakte/', {
      params: { person: personId, ...(nurAktuelle ? { nur_aktuelle: 1 } : {}) },
    }).then(r => r.data),

  /** Legt eine objektspezifische Untergliederung an ("05/A Hebeanlage"). */
  unterregisterAnlegen: (eingabe: UnterregisterEingabe) =>
    client.post('/aktenregister/', eingabe).then(r => r.data),

  unterregisterLoeschen: (id: string) =>
    client.delete(`/aktenregister/${id}/`),

  /** Setzt das Register eines Dokuments; null nimmt es wieder heraus. */
  einsortieren: (dokumentId: string, registerId: string | null) =>
    client.post(`/dokumente/${dokumentId}/einsortieren/`, { register: registerId })
      .then(r => r.data),
}
