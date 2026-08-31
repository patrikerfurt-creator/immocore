import axios from 'axios'
import client from './client'
import type { IbanCheckResult } from '../components/ui/IbanInput'

/**
 * API-Zugriff des Eigentümer-Portals (Spec 1a).
 *
 * Eigener axios-Client mit eigenem Token-Speicher: das Portal-Token darf
 * nicht in denselben localStorage-Schlüssel wie das Mitarbeiter-JWT
 * geschrieben werden, sonst würde ein Portal-Login den internen Login im
 * selben Browser überschreiben (und umgekehrt). Auch das Auth-Schema ist
 * ein anderes ("Portal" statt "Bearer") — so kann ein Token niemals in
 * der falschen Auth-Kette landen.
 */
const PORTAL_TOKEN_KEY = 'portal_token'

export function getPortalToken(): string | null {
  return localStorage.getItem(PORTAL_TOKEN_KEY)
}

export function setPortalToken(token: string) {
  localStorage.setItem(PORTAL_TOKEN_KEY, token)
}

export function clearPortalToken() {
  localStorage.removeItem(PORTAL_TOKEN_KEY)
}

const portalClient = axios.create({
  baseURL: '/api/v1/portal',
  headers: { 'Content-Type': 'application/json' },
})

portalClient.interceptors.request.use((config) => {
  const token = getPortalToken()
  if (token) {
    config.headers.Authorization = `Portal ${token}`
  }
  return config
})

// Kein stiller Token-Refresh wie im internen Client: eine abgelaufene
// Portal-Sitzung führt zurück zur Anmeldung, wo ein neuer Magic Link
// angefordert wird. Ein Refresh-Token wäre ein zweites dauerhaftes
// Geheimnis im Browser, ohne dass der Eigentümer davon profitiert.
portalClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/portal/anmelden')) {
      clearPortalToken()
      if (window.location.pathname.startsWith('/portal')) {
        window.location.href = '/portal/login'
      }
    }
    return Promise.reject(error)
  },
)

export interface PortalEinheit {
  einheit_id: string
  einheit_nr: string
  lage: string
  nutzungsart: string
  miteigentumsanteil: string | null
  eigentum_seit: string
  eigentum_bis: string | null
}

export interface PortalWegKarte {
  objekt_id: string
  objektnummer: string
  bezeichnung: string
  strasse: string
  plz: string
  ort: string
  einheiten: PortalEinheit[]
}

export interface PortalMeineDaten {
  person_id: string
  personennummer: string
  name: string
  anrede: string
  strasse: string
  hausnummer: string
  plz: string
  ort: string
  telefon: string
  email: string
  email_pending: string
  iban: string
  bic: string
  hat_aktives_mandat: boolean
  mandatsreferenz: string | null
}

export interface PortalAnmeldeErgebnis {
  token: string
  gueltig_bis: string
  gueltig_stunden: number
  erstanmeldung: boolean
  name: string
}

/** Anonym — die Antwort ist bewusst immer gleich (Enumeration-Schutz). */
export async function magicLinkAnfordern(email: string): Promise<{ detail: string }> {
  const { data } = await axios.post('/api/v1/portal/auth/magic-link/request/', { email })
  return data
}

export async function tokenEinloesen(token: string): Promise<PortalAnmeldeErgebnis> {
  const { data } = await axios.post<PortalAnmeldeErgebnis>(
    '/api/v1/portal/auth/magic-link/verify/', { token },
  )
  setPortalToken(data.token)
  return data
}

export async function abmelden(): Promise<void> {
  try {
    await portalClient.post('/auth/logout/')
  } finally {
    clearPortalToken()
  }
}

export async function meineEinheiten(): Promise<PortalWegKarte[]> {
  const { data } = await portalClient.get<PortalWegKarte[]>('/meine-einheiten/')
  return data
}

export async function meineDaten(): Promise<PortalMeineDaten> {
  const { data } = await portalClient.get<PortalMeineDaten>('/meine-daten/')
  return data
}

export interface KontaktWerte {
  strasse?: string
  hausnummer?: string
  plz?: string
  ort?: string
  telefon?: string
}

export async function kontaktSpeichern(werte: KontaktWerte): Promise<PortalMeineDaten> {
  const { data } = await portalClient.patch<PortalMeineDaten>('/meine-daten/', werte)
  return data
}

/** IBAN-Prüfung während der Eingabe — eigener Endpunkt hinter der Portal-Sitzung. */
export async function ibanPruefen(iban: string): Promise<IbanCheckResult> {
  const { data } = await portalClient.get<IbanCheckResult>('/iban-check/', { params: { iban } })
  return data
}

export interface BankverbindungAntwort extends PortalMeineDaten {
  mandat_aktualisiert: boolean
  mandatsreferenz: string | null
}

export async function bankverbindungSpeichern(
  werte: { iban?: string; bic?: string },
): Promise<BankverbindungAntwort> {
  const { data } = await portalClient.patch<BankverbindungAntwort>(
    '/meine-daten/bankverbindung/', werte,
  )
  return data
}

export async function emailAendern(email: string): Promise<{ detail: string; email_pending: string }> {
  const { data } = await portalClient.post('/meine-daten/email/', { email })
  return data
}

/** Anonym — der Bestätigungslink wird oft im neuen Postfach geöffnet. */
export async function emailBestaetigen(token: string): Promise<{ detail: string; email: string }> {
  const { data } = await axios.post('/api/v1/portal/meine-daten/email/bestaetigen/', { token })
  return data
}

// ---------------------------------------------------------------------------
// Interner Bereich (Mitarbeiter-JWT) — Portal-Zugänge verwalten
// ---------------------------------------------------------------------------

export interface PortalZugangVerwaltung {
  id: string
  person_id: string
  person_name: string
  email: string
  status: 'eingeladen' | 'aktiv' | 'gesperrt'
  aktiv: boolean
  eingeladen_am: string
  eingeladen_von: string
  erstaktivierung_am: string | null
  letzter_login: string | null
  email_pending: string
}

// Diese Aufrufe laufen über den internen Client (Mitarbeiter-JWT), nicht
// über portalClient — es sind Verwaltungsfunktionen, keine Portalfunktionen.
export async function portalZugaengeLaden(personId: string): Promise<PortalZugangVerwaltung[]> {
  const { data } = await client.get<PortalZugangVerwaltung[]>(
    '/portal-verwaltung/zugaenge/', { params: { person: personId } },
  )
  return data
}

export async function portalEinladen(personId: string): Promise<PortalZugangVerwaltung> {
  const { data } = await client.post<PortalZugangVerwaltung>(
    '/portal-verwaltung/zugaenge/einladen/', { person_id: personId },
  )
  return data
}

export async function portalZugangSperren(zugangId: string): Promise<PortalZugangVerwaltung> {
  const { data } = await client.post(`/portal-verwaltung/zugaenge/${zugangId}/sperren/`)
  return data
}

export async function portalZugangEntsperren(zugangId: string): Promise<PortalZugangVerwaltung> {
  const { data } = await client.post(`/portal-verwaltung/zugaenge/${zugangId}/entsperren/`)
  return data
}
