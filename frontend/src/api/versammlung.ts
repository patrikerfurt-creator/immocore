import client from './client'
import type {
  EVAbschlussErgebnis,
  EVAnfechtungStatus,
  EVAnwesenheitPayload,
  EVBeschluss,
  EVCreatePayload,
  EVDetail,
  EVEinladungPdfErgebnis,
  EVEreignis,
  EVList,
  EVProtokollUploadErgebnis,
  EVQuorum,
  EVQuorumJeStimmgrundlage,
  EVStimme,
  EVStimmgrundlage,
  EVStimmkraftErgebnis,
  EVTeilnehmer,
  EVVotum,
  EVVersandErgebnis,
  EVVersandplan,
  EVVersandprotokoll,
  Tagesordnungspunkt,
  TagesordnungspunktCreatePayload,
  Versammlungsort,
} from '../types'

export const versammlungApi = {
  list: (params?: Record<string, string>) =>
    client.get<EVList[]>('/versammlungen/', { params }).then(r => r.data),
  get: (id: string) => client.get<EVDetail>(`/versammlungen/${id}/`).then(r => r.data),
  create: (data: EVCreatePayload) =>
    client.post<EVDetail>('/versammlungen/', data).then(r => r.data),
  update: (id: string, data: Partial<EVDetail>) =>
    client.patch<EVDetail>(`/versammlungen/${id}/`, data).then(r => r.data),

  // Task-Fortschritt — Statuswechsel passieren ausschließlich serverseitig.
  taskErledigt: (id: string, taskNr: number) =>
    client.post<EVDetail>(`/versammlungen/${id}/task-erledigt/`, { task_nr: taskNr })
      .then(r => r.data),
  taskZuruecksetzen: (id: string, taskNr: number, grund: string) =>
    client.post<EVDetail>(`/versammlungen/${id}/task-zuruecksetzen/`, {
      task_nr: taskNr, grund,
    }).then(r => r.data),

  ereignisse: (id: string) =>
    client.get<EVEreignis[]>(`/versammlungen/${id}/ereignisse/`).then(r => r.data),

  // Tagesordnung
  tagesordnung: (id: string) =>
    client.get<{ tagesordnung: Tagesordnungspunkt[]; probleme: string[] }>(
      `/versammlungen/${id}/tagesordnung/`,
    ).then(r => r.data),
  topAnlegen: (data: TagesordnungspunktCreatePayload) =>
    client.post<Tagesordnungspunkt>('/tagesordnungspunkte/', data).then(r => r.data),
  topAendern: (
    topId: string,
    // stimmgrundlage_id (statt stimmgrundlage) ist das write-only PATCH-Feld
    // des Serializers (siehe TagesordnungspunktSerializer.stimmgrundlage_id).
    data: Partial<Tagesordnungspunkt> & { stimmgrundlage_id?: string | null },
  ) =>
    client.patch<Tagesordnungspunkt>(`/tagesordnungspunkte/${topId}/`, data)
      .then(r => r.data),
  topLoeschen: (topId: string) => client.delete(`/tagesordnungspunkte/${topId}/`),

  // Teilnehmer und Stimmkraft
  teilnehmerErmitteln: (id: string) =>
    client.post<EVStimmkraftErgebnis>(`/versammlungen/${id}/teilnehmer-ermitteln/`, {})
      .then(r => r.data),
  teilnehmer: (id: string) =>
    client.get<EVTeilnehmer[]>(`/versammlungen/${id}/teilnehmer/`).then(r => r.data),

  // Einladung und Versand
  einladungPdfErzeugen: (id: string, anlagenIds: string[] = []) =>
    client.post<EVEinladungPdfErgebnis>(`/versammlungen/${id}/einladung-pdf/`, {
      anlagen_ids: anlagenIds,
    }).then(r => r.data),
  versandplan: (id: string) =>
    client.get<EVVersandplan>(`/versammlungen/${id}/versandplan/`).then(r => r.data),
  // sofort=true versendet im Request und liefert das Ergebnis direkt — nur für
  // kleine Gemeinschaften. Ohne sofort läuft der Versand über Celery (HTTP 202).
  einladungenVersenden: (
    id: string,
    plan: Record<string, string>,
    sofort = false,
  ) =>
    client.post<EVVersandErgebnis | { detail: string; anzahl_empfaenger: number }>(
      `/versammlungen/${id}/einladungen-versenden/`, { plan, sofort },
    ).then(r => ({ status: r.status, daten: r.data })),
  versandprotokoll: (id: string) =>
    client.get<EVVersandprotokoll[]>(`/versammlungen/${id}/versandprotokoll/`)
      .then(r => r.data),

  // Stimmgrundlagen (Spec v1.1 Kap. 2)
  stimmgrundlagen: (id: string) =>
    client.get<EVStimmgrundlage[]>(`/versammlungen/${id}/stimmgrundlagen/`)
      .then(r => r.data),
  stimmgrundlageHinzufuegen: (id: string, daten: {
    verteilerschluessel?: string | null
    ist_kopfprinzip?: boolean
    wirtschaftsjahr?: number
    ist_standard?: boolean
  }) =>
    client.post<EVStimmgrundlage>(
      `/versammlungen/${id}/stimmgrundlage-hinzufuegen/`, daten,
    ).then(r => r.data),

  // Checkout / Checkout-Rücknahme / Abschluss / Protokoll-Upload
  // (Spec v1.1 Kap. 4, ersetzt Task 4+5)
  checkout: (id: string) =>
    client.post<EVDetail>(`/versammlungen/${id}/checkout/`, {}).then(r => r.data),
  checkoutZuruecknehmen: (id: string, grund: string) =>
    client.post<EVDetail>(`/versammlungen/${id}/checkout-zuruecknehmen/`, { grund })
      .then(r => r.data),
  abschluss: (id: string) =>
    client.post<EVAbschlussErgebnis>(`/versammlungen/${id}/abschluss/`, {})
      .then(r => r.data),
  protokollUpload: (id: string, datei: File) => {
    const formData = new FormData()
    formData.append('datei', datei)
    return client.post<EVProtokollUploadErgebnis>(
      `/versammlungen/${id}/protokoll-upload/`, formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    ).then(r => r.data)
  },
  quorumJeStimmgrundlage: (id: string) =>
    client.get<EVQuorumJeStimmgrundlage>(`/versammlungen/${id}/quorum/`)
      .then(r => r.data),
}

// Baut aus einem Katalogeintrag den maßgeblichen Ort-Text (GoBD-Snapshot), der
// in das Feld ``ort`` übernommen wird — der Katalog dient nur der Vorbelegung.
export function ortAusKatalog(vo: Versammlungsort): string {
  const plzOrt = [vo.plz, vo.ort_text].filter(Boolean).join(' ').trim()
  return [vo.bezeichnung, vo.strasse, plzOrt, vo.zusatz]
    .map(t => t.trim())
    .filter(Boolean)
    .join(', ')
}

export const versammlungsortApi = {
  list: () => client.get<Versammlungsort[]>('/versammlungsorte/').then(r => r.data),
  get: (id: string) =>
    client.get<Versammlungsort>(`/versammlungsorte/${id}/`).then(r => r.data),
  create: (data: Partial<Versammlungsort>) =>
    client.post<Versammlungsort>('/versammlungsorte/', data).then(r => r.data),
  update: (id: string, data: Partial<Versammlungsort>) =>
    client.patch<Versammlungsort>(`/versammlungsorte/${id}/`, data).then(r => r.data),
}

// --- Phase D: Durchführung und Beschlussfassung ---

export const versammlungDurchfuehrungApi = {
  quorum: (id: string) =>
    client.get<EVQuorum>(`/versammlungen/${id}/quorum/`).then(r => r.data),

  anwesenheit: (teilnehmerId: string, daten: EVAnwesenheitPayload) =>
    client.patch<EVTeilnehmer>(`/ev-teilnehmer/${teilnehmerId}/`, daten)
      .then(r => r.data),

  abstimmung: (topId: string, ja: string, nein: string, enthaltung: string,
               bemerkung?: string) =>
    client.post<Tagesordnungspunkt>(`/tagesordnungspunkte/${topId}/abstimmung/`, {
      ja, nein, enthaltung, bemerkung,
    }).then(r => r.data),

  einzelstimmen: (topId: string, voten: Record<string, EVVotum>) =>
    client.post<Tagesordnungspunkt>(`/tagesordnungspunkte/${topId}/einzelstimmen/`, {
      voten,
    }).then(r => r.data),

  stimmen: (topId: string) =>
    client.get<EVStimme[]>(`/tagesordnungspunkte/${topId}/stimmen/`).then(r => r.data),

  ergebnisStatus: (topId: string, ergebnis: 'vertagt' | 'entfallen', bemerkung = '') =>
    client.post<Tagesordnungspunkt>(
      `/tagesordnungspunkte/${topId}/ergebnis-status/`, { ergebnis, bemerkung },
    ).then(r => r.data),

  beschluesseDerEv: (id: string) =>
    client.get<EVBeschluss[]>(`/versammlungen/${id}/beschluesse/`).then(r => r.data),
}

export const beschlussApi = {
  list: (params?: Record<string, string>) =>
    client.get<EVBeschluss[]>('/beschluesse/', { params }).then(r => r.data),
  get: (id: string) => client.get<EVBeschluss>(`/beschluesse/${id}/`).then(r => r.data),
  anfechtung: (id: string, daten: {
    anfechtung_status: EVAnfechtungStatus
    notiz?: string
    aufgehoben_am?: string | null
    gerichtlicher_hinweis?: string
  }) =>
    client.post<EVBeschluss>(`/beschluesse/${id}/anfechtung/`, daten).then(r => r.data),
}
