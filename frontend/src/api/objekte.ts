import client from './client'
import type { Objekt, ObjektList, Einheit, Eingang, Bankkonto, Verteilerschluessel, VerteilerschluesselWert, MahnEinstellung } from '../types'

export const objekteApi = {
  list: () => client.get<ObjektList[]>('/objekte/').then(r => r.data),
  get: (id: string) => client.get<Objekt>(`/objekte/${id}/`).then(r => r.data),
  create: (data: Partial<Objekt>) => client.post<Objekt>('/objekte/', data).then(r => r.data),
  update: (id: string, data: Partial<Objekt>) => client.patch<Objekt>(`/objekte/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/objekte/${id}/`),

  // Mahn-Konfiguration (404 = noch nicht konfiguriert)
  getMahnEinstellung: (objektId: string) =>
    client.get<MahnEinstellung>(`/objekte/${objektId}/mahn-einstellung/`).then(r => r.data),
  putMahnEinstellung: (objektId: string, data: MahnEinstellung) =>
    client.put<MahnEinstellung>(`/objekte/${objektId}/mahn-einstellung/`, data).then(r => r.data),

  // Einheiten
  listEinheiten: (params?: Record<string, string>) =>
    client.get<Einheit[]>('/einheiten/', { params }).then(r => r.data),
  createEinheit: (data: Partial<Einheit>) => client.post<Einheit>('/einheiten/', data).then(r => r.data),
  // Einzelne Einheit zu bestehendem Objekt anlegen (Admin): legt die Einheit an und
  // zieht Verteilerschlüssel-Werte (MEA/Fläche) nach. 403 für Nicht-Administratoren.
  anlegenEinheit: (data: {
    objekt: string
    einheit_nr: string
    einheit_typ: string
    lage: string
    eingang?: string | null
    flaechennummer?: string
    mea?: string
    flaeche_qm?: string
    umsatzsteuer_abrechnungsart?: string | null
  }) => client.post<Einheit>('/einheiten/anlegen/', data).then(r => r.data),
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
      rows: Array<{
        zeile: number
        status: string
        aktion: 'importieren' | 'ablehnen'
        fehler: string[]
        hinweis: string
        daten: Record<string, string | null>
      }>
      ok_anzahl: number
      duplikat_anzahl: number
      fehler_anzahl: number
      gesamt: number
    }>('/einheiten/csv-vorschau/', fd, { headers: { 'Content-Type': undefined } }).then(r => r.data)
  },
  csvImportEinheiten: (rows: Array<Record<string, unknown>>, modus: 'ergaenzen' | 'neuimport' = 'ergaenzen') =>
    client.post<{ angelegt: number; geloescht: number; fehler: string[] }>(
      '/einheiten/csv-import/', { rows, modus }
    ).then(r => r.data),

  // Wirtschaftsjahre
  wirtschaftsjahre: (objektId: string) =>
    client.get<Array<{ id: string; jahr: number; status: string; beginn_monat: number }>>(
      '/wirtschaftsjahre/', { params: { objekt: objektId } }
    ).then(r => r.data),

  // Eingänge
  listEingaenge: (objektId: string) =>
    client.get<Eingang[]>('/eingaenge/', { params: { objekt: objektId } }).then(r => r.data),
  createEingang: (data: Partial<Eingang>) => client.post<Eingang>('/eingaenge/', data).then(r => r.data),
  updateEingang: (id: string, data: Partial<Eingang>) => client.patch<Eingang>(`/eingaenge/${id}/`, data).then(r => r.data),
  deleteEingang: (id: string) => client.delete(`/eingaenge/${id}/`),

  // Bankkonten
  createBankkonto: (data: Partial<Bankkonto>) => client.post<Bankkonto>('/bankkonten/', data).then(r => r.data),
  updateBankkonto: (id: string, data: Partial<Bankkonto>) => client.patch<Bankkonto>(`/bankkonten/${id}/`, data).then(r => r.data),
  deleteBankkonto: (id: string) => client.delete(`/bankkonten/${id}/`),

  // Verteilerschlüssel (Flächen / MEA)
  verteilerschluessel: (params?: Record<string, string>) =>
    client.get<Verteilerschluessel[]>('/verteilerschluessel/', { params }).then(r => r.data),
  createVerteilerschluessel: (data: Partial<Verteilerschluessel>) =>
    client.post<Verteilerschluessel>('/verteilerschluessel/', data).then(r => r.data),
  wertSetzen: (schluesselId: string, einheitId: string, wert: string, wirtschaftsjahr = 0) =>
    client.post<VerteilerschluesselWert>(
      `/verteilerschluessel/${schluesselId}/wert-setzen/`,
      { einheit: einheitId, wert, wirtschaftsjahr }
    ).then(r => r.data),
  deleteWert: (wertId: string) =>
    client.delete(`/verteilerschluessel-werte/${wertId}/`),
  vsKopieren: (objektId: string, quellWj: number, zielWj: number) =>
    client.post<{ kopiert: number; quell_wj: number; ziel_wj: number }>(
      `/objekte/${objektId}/vs-kopieren/`,
      { quell_wj: quellWj, ziel_wj: zielWj }
    ).then(r => r.data),

  // MEA-Import (Excel) je Liegenschaft — setzt Schlüssel 010 auf vorhandene Einheiten
  meaVorschau: (objektId: string, file: File) => {
    const fd = new FormData()
    fd.append('datei', file)
    return client.post<MeaVorschau>(
      `/objekte/${objektId}/mea-vorschau/`, fd,
      { headers: { 'Content-Type': undefined } }
    ).then(r => r.data)
  },
  meaCommit: (objektId: string, rows: MeaVorschauZeile[]) =>
    client.post<{ aktualisiert: number; uebersprungen: number; fehler: string[]; summe: string }>(
      `/objekte/${objektId}/mea-commit/`, { rows }
    ).then(r => r.data),
}

export type MeaStatus = 'ok' | 'nicht_gefunden' | 'fremdes_objekt' | 'kein_wert' | 'doppelt'

export type MeaVorschauZeile = {
  zeile: number
  status: MeaStatus
  meldung: string
  flaechennummer: string
  objektnummer: string
  einheit_nr: string
  lage: string
  alt_wert: string
  neu_wert: string
  daten: { einheit_id: string | null; wert: string | null }
}

export type MeaVorschau = {
  zeilen: MeaVorschauZeile[]
  summary: {
    objektnummer: string
    objektnummer_datei: string[]
    gesamt: number
    ok: number
    nicht_gefunden: number
    fremdes_objekt: number
    kein_wert: number
    doppelt: number
    einheiten_gesamt: number
    einheiten_ohne_zeile: Array<{ flaechennummer: string; einheit_nr: string }>
    summe: string
  }
}
