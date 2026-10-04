import { isAxiosError } from 'axios'
import client from './client'
import type {
  Briefbogen, BriefbogenPayload, Druckstapel, DruckstapelCreatePayload, Platzhalter, Schreiben,
  SchreibenCreatePayload, SchreibenDetail, SchreibenListeParams, SchreibenVersandAntwort,
  Serienlauf, SerienlaufCreatePayload, Textbaustein, TextbausteinPayload,
  Vorlage, VorlageCreatePayload, VorlageUpdatePayload, VorlagenAssistentAnfrage,
  VorlagenAssistentResponse, VorlagenBlock, VorlagenVersion, VorlagenVersionPayload,
  VorlagenVersionVorschauPayload,
} from '../types'

// Alle Endpunkte liegen unter /api/v1/korrespondenz/ (Spec Abschnitt 8).
// Phase 5c (Schreiben, Postausgang, Druckstapel, Serienlauf) ergänzt weitere
// Objekte in dieser Datei, ohne die vorhandenen zu ändern.
// PDF-Endpunkte: mit dem Standard-Accept aufrufen (KEIN `Accept: application/pdf`,
// sonst 406) und die Antwort als Blob lesen.
const BASIS = '/korrespondenz'

/** Synchroner KI-Aufruf: Backend-Timeout 60 s (Spec 6), Client wartet etwas länger. */
export const ASSISTENT_TIMEOUT_MS = 65_000

export const platzhalterApi = {
  list: (anlass: string) =>
    client.get<Platzhalter[]>(`${BASIS}/platzhalter/`, { params: { anlass } }).then(r => r.data),
}

export const vorlagenApi = {
  list: (params?: Record<string, string>) =>
    client.get<Vorlage[]>(`${BASIS}/vorlagen/`, { params }).then(r => r.data),
  get: (id: string) => client.get<Vorlage>(`${BASIS}/vorlagen/${id}/`).then(r => r.data),
  create: (data: VorlageCreatePayload) =>
    client.post<Vorlage>(`${BASIS}/vorlagen/`, data).then(r => r.data),
  update: (id: string, data: VorlageUpdatePayload) =>
    client.patch<Vorlage>(`${BASIS}/vorlagen/${id}/`, data).then(r => r.data),

  // Versionen einer Vorlage
  versionen: (vorlageId: string) =>
    client.get<VorlagenVersion[]>(`${BASIS}/vorlagen/${vorlageId}/versionen/`).then(r => r.data),
  versionAnlegen: (vorlageId: string, data: VorlagenVersionPayload = {}) =>
    client.post<VorlagenVersion>(`${BASIS}/vorlagen/${vorlageId}/versionen/`, data).then(r => r.data),
}

export const vorlagenVersionenApi = {
  /** Nur im Status `entwurf` erlaubt (Backend lehnt sonst mit 400 ab). */
  update: (versionId: string, data: VorlagenVersionPayload) =>
    client.patch<VorlagenVersion>(`${BASIS}/versionen/${versionId}/`, data).then(r => r.data),
  /** Braucht die Permission `korrespondenz.vorlage_freigeben` (sonst 403). */
  freigeben: (versionId: string) =>
    client.post<VorlagenVersion>(`${BASIS}/versionen/${versionId}/freigeben/`).then(r => r.data),
  /** PDF auf dem echten Briefbogen gegen einen Beispiel-Empfänger. */
  vorschau: (versionId: string, data: VorlagenVersionVorschauPayload) =>
    client.post<Blob>(`${BASIS}/versionen/${versionId}/vorschau/`, data, {
      responseType: 'blob',
    }).then(r => r.data),
}

export const textbausteineApi = {
  list: (params?: Record<string, string>) =>
    client.get<Textbaustein[]>(`${BASIS}/textbausteine/`, { params }).then(r => r.data),
  get: (id: string) => client.get<Textbaustein>(`${BASIS}/textbausteine/${id}/`).then(r => r.data),
  create: (data: TextbausteinPayload) =>
    client.post<Textbaustein>(`${BASIS}/textbausteine/`, data).then(r => r.data),
  update: (id: string, data: TextbausteinPayload) =>
    client.patch<Textbaustein>(`${BASIS}/textbausteine/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`${BASIS}/textbausteine/${id}/`),
}

/** IsAdminUser: für normale Mitarbeiter antwortet das Backend mit 403. */
export const briefboegenApi = {
  list: () => client.get<Briefbogen[]>(`${BASIS}/briefboegen/`).then(r => r.data),
  get: (id: string) => client.get<Briefbogen>(`${BASIS}/briefboegen/${id}/`).then(r => r.data),
  create: (data: BriefbogenPayload) =>
    client.post<Briefbogen>(`${BASIS}/briefboegen/`, data).then(r => r.data),
  update: (id: string, data: BriefbogenPayload) =>
    client.patch<Briefbogen>(`${BASIS}/briefboegen/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`${BASIS}/briefboegen/${id}/`),
}

/**
 * KI-Assistent im Vorlagen-Editor (Spec 6) — nie beim Erzeugen eines Schreibens.
 * Nicht verfügbar (kein ANTHROPIC_API_KEY): das Backend meldet 501/503 bzw.
 * `verfuegbar: false`; die UI blendet die Buttons dann aus (siehe
 * `istAssistentNichtVerfuegbar`).
 */
export const vorlagenAssistentApi = {
  entwerfen: (data: VorlagenAssistentAnfrage) =>
    client.post<VorlagenAssistentResponse>(`${BASIS}/vorlagen-assistent/`, data, {
      timeout: ASSISTENT_TIMEOUT_MS,
    }).then(r => r.data),

  /**
   * Optionale Vorabprüfung. Der Vertrag (Spec 8) sieht nur POST vor; ein GET
   * ohne Antwortfeld `verfuegbar: false` gilt deshalb als „unbekannt = verfügbar".
   */
  verfuegbar: async (): Promise<boolean> => {
    try {
      const r = await client.get<{ verfuegbar?: boolean }>(`${BASIS}/vorlagen-assistent/`)
      return r.data?.verfuegbar !== false
    } catch (error) {
      return !istAssistentNichtVerfuegbar(error)
    }
  },
}

/** Schreiben und Postausgang (Spec 7.1, 7.2, 8). */
export const schreibenApi = {
  /** Ohne `status`: Postausgang (zur Prüfung, nicht erzeugbar, Versand fehlgeschlagen). */
  list: (params?: SchreibenListeParams) =>
    client.get<Schreiben[]>(`${BASIS}/schreiben/`, { params }).then(r => r.data),
  get: (id: string) => client.get<SchreibenDetail>(`${BASIS}/schreiben/${id}/`).then(r => r.data),
  /** Legt das Schreiben an und rendert sofort: `zur_pruefung`, oder `entwurf` mit `fehler`. */
  create: (data: SchreibenCreatePayload) =>
    client.post<SchreibenDetail>(`${BASIS}/schreiben/`, data).then(r => r.data),
  /** Textanpassung — nur bei `einzeln_bearbeitbar` und Status `zur_pruefung`. */
  anpassen: (id: string, inhaltAngepasst: VorlagenBlock[]) =>
    client.patch<SchreibenDetail>(`${BASIS}/schreiben/${id}/`, { inhalt_angepasst: inhaltAngepasst })
      .then(r => r.data),
  freigeben: (id: string) =>
    client.post<SchreibenDetail>(`${BASIS}/schreiben/${id}/freigeben/`).then(r => r.data),
  /** `kanal: 'brief'` erzwingt den Brief (z. B. nach fehlgeschlagener E-Mail). */
  versenden: (id: string, kanal?: 'brief') =>
    client.post<SchreibenVersandAntwort>(`${BASIS}/schreiben/${id}/versenden/`, kanal ? { kanal } : {})
      .then(r => r.data),
  verwerfen: (id: string) =>
    client.post<SchreibenDetail>(`${BASIS}/schreiben/${id}/verwerfen/`).then(r => r.data),
  /** Vorschau (zur_pruefung) bzw. abgelegtes PDF. */
  pdf: (id: string) =>
    client.get<Blob>(`${BASIS}/schreiben/${id}/pdf/`, { responseType: 'blob' }).then(r => r.data),
}

/** Druckstapel (Spec 7.3): Sammel-PDF der druckbereiten Briefe. */
export const druckstapelApi = {
  erzeugen: (data: DruckstapelCreatePayload = {}) =>
    client.post<Druckstapel>(`${BASIS}/druckstapel/`, data).then(r => r.data),
  /** „gedruckt und kuvertiert“: setzt `versendet_am` der Schreiben. */
  bestaetigen: (id: string) =>
    client.post<Druckstapel>(`${BASIS}/druckstapel/${id}/bestaetigen/`).then(r => r.data),
  /** Sammel-PDF: liegt als Dokument im DMS (`Druckstapel.dokument`). */
  pdf: (dokumentId: string) =>
    client.get<Blob>(`/dokumente/${dokumentId}/datei/`, { responseType: 'blob' }).then(r => r.data),
}

/** Serienbrief-Läufe (Spec 7.4): Anlegen erzeugt sofort alle Schreiben (`zur_pruefung`). */
export const serienlaeufeApi = {
  erzeugen: (data: SerienlaufCreatePayload) =>
    client.post<Serienlauf>(`${BASIS}/serienlaeufe/`, data).then(r => r.data),
  get: (id: string) => client.get<Serienlauf>(`${BASIS}/serienlaeufe/${id}/`).then(r => r.data),
  /** 202: Mails/Druckstapel werden im Hintergrund verarbeitet (Status per `get` nachladen). */
  freigeben: (id: string) =>
    client.post<Serienlauf>(`${BASIS}/serienlaeufe/${id}/freigeben/`).then(r => r.data),
}

/** True, wenn ein Fehler des Assistenten „KI nicht konfiguriert / nicht verfügbar" bedeutet. */
export function istAssistentNichtVerfuegbar(error: unknown): boolean {
  if (!isAxiosError(error)) return false
  const status = error.response?.status
  if (status === 501 || status === 503) return true
  const data = error.response?.data as { verfuegbar?: boolean } | undefined
  return data?.verfuegbar === false
}

function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

/**
 * Fehlertext aus einer Axios-Antwort. Bei `responseType: 'blob'` (PDF-Vorschau)
 * steckt die JSON-Fehlermeldung des Backends in einem Blob und wird asynchron gelesen.
 */
export async function korrespondenzFehlerText(error: unknown, fallback: string): Promise<string> {
  if (!isAxiosError(error)) return fallback
  let data: unknown = error.response?.data
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    try {
      data = JSON.parse(await blobText(data))
    } catch {
      return fallback
    }
  }
  if (!data) return fallback
  if (typeof data === 'string') return data
  const obj = data as Record<string, unknown>
  if (obj.detail) return String(obj.detail)
  const werte = Object.values(obj).flat()
  return werte.length > 0 ? werte.join(' ') : fallback
}
