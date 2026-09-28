import client from './client'

/**
 * Mail-Posteingang: eingegangene Mails, die der Import nicht zuordnen konnte.
 *
 * Die Mails liegen bereits vollständig im DMS — Aufbewahrung und Zuordnung
 * sind getrennt. Hier fehlt ihnen nur die Verortung, die ein Mensch setzt.
 */
export type PosteingangStatus =
  | 'automatisch'
  | 'offen'
  | 'zugeordnet'
  | 'abgelegt'
  | 'verworfen'

export interface PosteingangDokument {
  id: string
  dateiname: string
  kategorie: string
  dokument_typ: string
  zugeordnet: boolean
}

export interface PosteingangMail {
  id: string
  dateiname: string
  absender: string
  absender_name: string
  betreff: string
  gesendet_am: string | null
  body_auszug: string
  anhaenge_anzahl: number
  status: string
  status_anzeige: string
  posteingang_status: PosteingangStatus
  posteingang_status_anzeige: string
  // Was die automatische Erkennung versucht hat — Entscheidungshilfe.
  person: string | null
  person_name: string | null
  objekt: string | null
  objekt_bezeichnung: string | null
  einheit: string | null
  einheit_nr: string | null
  zuordnung_quelle: string
  mehrdeutig: boolean
  personen_treffer: number
  ki_typ_code: string
  ki_prioritaet: string
  ki_betreff: string
  ki_konfidenz: string | null
  ki_begruendung: string
  vorgang: string | null
  vorgang_nummer: string | null
  erledigt_am: string | null
  erledigt_von_name: string | null
  erledigt_notiz: string
  dokumente: PosteingangDokument[]
  verarbeitet_am: string
}

export interface VorgangAnlegenEingabe {
  typ: string
  objekt?: string | null
  einheit?: string | null
  person?: string | null
  betreff?: string
  prioritaet?: string
  notiz?: string
}

export interface NurAblegenEingabe {
  objekt?: string | null
  einheit?: string | null
  person?: string | null
  notiz?: string
}

const BASIS = '/mail-posteingang'

export const mailPosteingangApi = {
  /** Ohne Angabe: nur offene Mails — das ist die Arbeitsliste. */
  async list(posteingangStatus?: PosteingangStatus | 'alle'): Promise<PosteingangMail[]> {
    const { data } = await client.get(`${BASIS}/`, {
      params: posteingangStatus ? { posteingang_status: posteingangStatus } : undefined,
    })
    // Die Liste kann paginiert kommen — nie der `next`-URL folgen, die ist
    // absolut und scheitert hinter dem Proxy.
    return Array.isArray(data) ? data : data.results
  },

  async detail(id: string): Promise<PosteingangMail> {
    const { data } = await client.get(`${BASIS}/${id}/`)
    return data
  },

  async vorgangAnlegen(id: string, eingabe: VorgangAnlegenEingabe): Promise<PosteingangMail> {
    const { data } = await client.post(`${BASIS}/${id}/vorgang-anlegen/`, eingabe)
    return data
  },

  async vorgangZuordnen(id: string, vorgang: string, notiz = ''): Promise<PosteingangMail> {
    const { data } = await client.post(`${BASIS}/${id}/vorgang-zuordnen/`, { vorgang, notiz })
    return data
  },

  async nurAblegen(id: string, eingabe: NurAblegenEingabe): Promise<PosteingangMail> {
    const { data } = await client.post(`${BASIS}/${id}/nur-ablegen/`, eingabe)
    return data
  },

  async verwerfen(id: string, notiz: string): Promise<PosteingangMail> {
    const { data } = await client.post(`${BASIS}/${id}/verwerfen/`, { notiz })
    return data
  },
}
