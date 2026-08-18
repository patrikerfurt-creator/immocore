import axios from 'axios'
import client from './client'
import type {
  Gewerk,
  HandwerkerauftragCreatePayload,
  HandwerkerauftragDetail,
  HandwerkerauftragList,
  Kreditor,
  ObjektHandwerker,
  OeffentlicherAuftrag,
  OeffentlicherAuftragBestaetigungErgebnis,
  PaginatedResponse,
} from '../types'

// ── Interne API (angemeldete Mitarbeiter) ──────────────────────────────
export const handwerkerApi = {
  // Dashboard/Detail — GET /handwerkerauftraege/ ist PAGINIERT (count/results),
  // als einziger paginierter Endpunkt im Projekt (Orchestrator-Vorgabe).
  list: (params?: Record<string, string | number>) =>
    client.get<PaginatedResponse<HandwerkerauftragList>>('/handwerkerauftraege/', { params }).then(r => r.data),
  get: (id: string) =>
    client.get<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/`).then(r => r.data),
  create: (data: HandwerkerauftragCreatePayload) =>
    client.post<HandwerkerauftragDetail>('/handwerkerauftraege/', data).then(r => r.data),
  erstelleAusVorgang: (vorgangId: string, data: HandwerkerauftragCreatePayload) =>
    client.post<HandwerkerauftragDetail>(`/vorgaenge/${vorgangId}/handwerkerauftrag/`, data).then(r => r.data),

  statusWechseln: (id: string, statusWert: string, kommentar?: string, abschluss_notiz?: string) =>
    client.post<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/status/`, {
      status: statusWert, kommentar, abschluss_notiz,
    }).then(r => r.data),
  kommentieren: (id: string, text: string) =>
    client.post<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/kommentar/`, { text }).then(r => r.data),
  erneutVersenden: (id: string) =>
    client.post<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/erneut-versenden/`).then(r => r.data),
  rechnungZuordnen: (id: string, rechnungId: string) =>
    client.post<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/rechnung-zuordnen/`, { rechnung: rechnungId }).then(r => r.data),
  rechnungLoesen: (id: string, rechnungId: string) =>
    client.post<HandwerkerauftragDetail>(`/handwerkerauftraege/${id}/rechnung-loesen/`, { rechnung: rechnungId }).then(r => r.data),

  // Gewerke
  gewerke: () => client.get<Gewerk[]>('/gewerke/').then(r => r.data),
  gewerkeAdmin: {
    list: () => client.get<Gewerk[]>('/gewerke/admin/').then(r => r.data),
    create: (data: Partial<Gewerk>) => client.post<Gewerk>('/gewerke/admin/', data).then(r => r.data),
    update: (id: string, data: Partial<Gewerk>) => client.patch<Gewerk>(`/gewerke/admin/${id}/`, data).then(r => r.data),
  },

  // Objekt-Handwerker-Zuordnung
  objektHandwerker: {
    list: (objektId: string) =>
      client.get<ObjektHandwerker[]>('/objekt-handwerker/', { params: { objekt: objektId } }).then(r => r.data),
    create: (data: { objekt: string; kreditor: string; prioritaet?: number; notiz?: string }) =>
      client.post<ObjektHandwerker>('/objekt-handwerker/', data).then(r => r.data),
    update: (id: string, data: Partial<Pick<ObjektHandwerker, 'prioritaet' | 'notiz'>>) =>
      client.patch<ObjektHandwerker>(`/objekt-handwerker/${id}/`, data).then(r => r.data),
    delete: (id: string) => client.delete(`/objekt-handwerker/${id}/`),
  },

  // Kreditoren, die als Handwerker markiert sind (für Auswahldialoge).
  // ACHTUNG: der Parameter "objekt" ist ein UND-Filter (liefert AUSSCHLIESSLICH
  // die diesem Objekt zugeordneten Handwerker, priorisiert) — kein "zuerst
  // diese, dann alle". Für "Hausfirmen zuerst, dann alle übrigen" müssen zwei
  // getrennte Abfragen kombiniert werden (siehe VorgangDetail/ObjektDetail).
  kreditorenHandwerker: (params?: { gewerk?: string; objekt?: string }) =>
    client.get<Kreditor[]>('/kreditoren/', {
      params: { ist_handwerker: 'true', ...(params?.gewerk ? { gewerk: params.gewerk } : {}), ...(params?.objekt ? { objekt: params.objekt } : {}) },
    }).then(r => r.data),

  /**
   * Best-effort-Ermittlung der bereits existierenden Handwerkeraufträge eines
   * Vorgangs.
   *
   * Abweichung/Limitation (siehe Abschlussbericht): weder der List- noch der
   * Objekt-Filter von GET /handwerkerauftraege/ kennen einen "vorgang"-Parameter,
   * und HandwerkerauftragListSerializer liefert kein "vorgang"-Feld (nur der
   * Detail-Serializer). Es gibt also serverseitig KEINE Möglichkeit, direkt
   * "alle Aufträge zu Vorgang X" abzufragen. Deshalb: zuerst objekt-gefiltert
   * (kleine, gebundene Ergebnismenge) laden, dann je Treffer das Detail (das
   * "vorgang" enthält) nachladen und clientseitig filtern. Erfordert eine
   * bekannte Objekt-ID — für Vorgänge ohne Objektbezug nicht anwendbar (siehe
   * VorgangDetail.tsx für den Umgang damit).
   */
  ladeFuerVorgang: async (vorgangId: string, objektId: string): Promise<HandwerkerauftragDetail[]> => {
    const seite = await client
      .get<PaginatedResponse<HandwerkerauftragList>>('/handwerkerauftraege/', {
        params: { objekt: objektId, page_size: 200 },
      })
      .then(r => r.data)
    const details = await Promise.all(
      seite.results.map(a => client.get<HandwerkerauftragDetail>(`/handwerkerauftraege/${a.id}/`).then(r => r.data)),
    )
    return details.filter(d => d.vorgang?.id === vorgangId)
  },
}

// ── Öffentliche API (kein Login — Auftragsbestätigung per Token) ───────
//
// SICHERHEITSKRITISCH: eigene axios-Instanz OHNE den Request-Interceptor aus
// client.ts (kein Authorization-Header) und OHNE dessen Response-Interceptor
// (kein Redirect auf /login bei 401/Token-Refresh). Ein Handwerker, der ohne
// Session auf /auftrag-bestaetigung/:token klickt, würde sonst — sobald der
// Server aus irgendeinem Grund 401 liefert, oder schlicht weil kein
// access_token im localStorage liegt und der Refresh fehlschlägt — auf die
// interne Login-Seite umgeleitet. Die öffentlichen Endpunkte sind serverseitig
// ohnehin AllowAny + authentication_classes=[] (siehe views_oeffentlich.py),
// hier muss also niemals ein Bearer-Token mitgeschickt werden.
const oeffentlicherClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

export const oeffentlicherAuftragApi = {
  get: (token: string) =>
    oeffentlicherClient.get<OeffentlicherAuftrag>(`/oeffentlich/auftrag/${token}/`).then(r => r.data),
  bestaetigen: (token: string, grund?: string) =>
    oeffentlicherClient
      .post<OeffentlicherAuftragBestaetigungErgebnis>(`/oeffentlich/auftrag/${token}/bestaetigen/`, grund ? { grund } : {})
      .then(r => r.data),
}
