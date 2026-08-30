import client from './client'

/**
 * Kreditor-Dublettenprüfung: angehaltene Kreditor-Neuanlagen aus dem
 * Rechnungsimport, die ein Mensch entscheiden muss.
 */
export type DublettenAnlass = 'fuzzy_name' | 'iban_abweichung' | 'name_abweichung'

export type DublettenStatus =
  | 'offen'
  | 'als_neu_angelegt'
  | 'zugeordnet'
  | 'abgelehnt'

export interface DublettenKandidat {
  id: string
  name: string
  kreditorennummer: string
  iban: string
  aktiv: boolean
  score: number
  match_typ: 'iban' | 'iban_zweitkonto' | 'name_exakt' | 'fuzzy'
}

export interface KreditorDublettenPruefung {
  id: string
  rechnung: string
  rechnung_dateiname: string
  rechnungsnummer: string
  rechnungsdatum: string | null
  betrag_brutto: string | null
  erkannter_name: string
  erkannte_iban: string
  anlass: DublettenAnlass
  anlass_text: string
  kandidaten: DublettenKandidat[]
  status: DublettenStatus
  status_text: string
  notiz: string
  ergebnis_kreditor: string | null
  ergebnis_kreditor_name: string
  entschieden_von_name: string
  entschieden_am: string | null
  erstellt_am: string
}

const BASIS = '/kreditor-dubletten'

export const kreditorDublettenApi = {
  /** Ohne Angabe: nur offene Fälle — das ist die Arbeitsliste. */
  list: (status?: DublettenStatus | 'alle') =>
    client
      .get<KreditorDublettenPruefung[]>(`${BASIS}/`, { params: status ? { status } : undefined })
      .then(r => r.data),

  get: (id: string) =>
    client.get<KreditorDublettenPruefung>(`${BASIS}/${id}/`).then(r => r.data),

  alsNeuAnlegen: (id: string, notiz = '') =>
    client
      .post<KreditorDublettenPruefung>(`${BASIS}/${id}/als-neu-anlegen/`, { notiz })
      .then(r => r.data),

  zuordnen: (id: string, kreditorId: string, ibanUebernehmen = true, notiz = '') =>
    client
      .post<KreditorDublettenPruefung>(`${BASIS}/${id}/zuordnen/`, {
        kreditor_id: kreditorId,
        iban_uebernehmen: ibanUebernehmen,
        notiz,
      })
      .then(r => r.data),

  ablehnen: (id: string, notiz = '') =>
    client
      .post<KreditorDublettenPruefung>(`${BASIS}/${id}/ablehnen/`, { notiz })
      .then(r => r.data),
}
