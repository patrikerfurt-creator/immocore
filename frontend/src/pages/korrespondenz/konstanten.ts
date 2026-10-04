import type { VorlagenAnlass, VorlagenKanal, VorlagenVersionStatus } from '../../types'

// Spiegel von Vorlage.ANLASS_CHOICES / KANAL_CHOICES / VorlagenVersion.STATUS_CHOICES (Backend).
export const ANLASS_LABEL: Record<VorlagenAnlass, string> = {
  eigentuemer_begruessung: 'Begrüßung neuer Eigentümer',
  eigentuemer_verabschiedung: 'Verabschiedung Voreigentümer',
  mahnung_stufe_1: 'Mahnung Stufe 1 (Zahlungserinnerung)',
  mahnung_stufe_2: 'Mahnung Stufe 2',
  mahnung_stufe_3: 'Mahnung Stufe 3 (letzte Mahnung)',
  etv_einladung: 'Einladung Eigentümerversammlung',
  eigentuemer_allgemein: 'Allgemeines Eigentümerschreiben',
  vorgang_antwort: 'Vorgangsantwort',
}

export const ANLASS_OPTIONEN = (Object.keys(ANLASS_LABEL) as VorlagenAnlass[]).map(value => ({
  value, label: ANLASS_LABEL[value],
}))

export const KANAL_LABEL: Record<VorlagenKanal, string> = {
  brief: 'Brief',
  email: 'E-Mail',
  beides: 'Brief und E-Mail',
}

export const VERSION_STATUS_LABEL: Record<VorlagenVersionStatus, string> = {
  entwurf: 'Entwurf',
  freigegeben: 'Freigegeben',
  abgeloest: 'Abgelöst',
}

/** Kurzform von `fehlerText` für synchrone Fehler (Axios-Response mit JSON). */
export function fehlerMeldung(error: unknown, fallback: string): string {
  // @ts-expect-error axios error shape
  const data = error?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return String(data.detail)
  const werte = Object.values(data as Record<string, unknown>).flat()
  return werte.length > 0 ? werte.join(' ') : fallback
}
