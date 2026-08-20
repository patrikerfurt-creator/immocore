import client from './client'
import type {
  EVAnfechtungStatus,
  EVAnwesenheitPayload,
  EVBeschluss,
  EVCreatePayload,
  EVDetail,
  EVEinladungPdfErgebnis,
  EVEreignis,
  EVList,
  EVQuorum,
  EVStimme,
  EVStimmkraftErgebnis,
  EVTeilnehmer,
  EVUebernahmeErgebnis,
  EVVotum,
  EVVersandErgebnis,
  EVVersandplan,
  EVVersandprotokoll,
  Tagesordnungspunkt,
  TagesordnungspunktCreatePayload,
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
  topAendern: (topId: string, data: Partial<Tagesordnungspunkt>) =>
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

  durchfuehrungAbschliessen: (id: string) =>
    client.post<EVDetail>(`/versammlungen/${id}/durchfuehrung-abschliessen/`, {})
      .then(r => r.data),

  beschluesseUebernehmen: (id: string) =>
    client.post<EVUebernahmeErgebnis>(`/versammlungen/${id}/beschluesse-uebernehmen/`, {})
      .then(r => r.data),

  protokollErzeugen: (id: string) =>
    client.post<EVEinladungPdfErgebnis>(`/versammlungen/${id}/protokoll-pdf/`, {})
      .then(r => r.data),

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
