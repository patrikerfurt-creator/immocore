import type { SerienlaufFilter } from '../../../types'

/** Einheitstypen (Spiegel von `Einheit.EINHEIT_TYP_CHOICES`). */
export const EINHEIT_TYPEN = ['Wohnung', 'Gewerbe', 'Stellplatz', 'Sonstiges']

/** Manuelle Ausnahme je Eigentumsverhältnis: aus dem Kreis nehmen bzw. zusätzlich aufnehmen. */
export type Ausnahme = 'aus' | 'zu'

export interface EmpfaengerAuswahl {
  einheit_typ: string[]
  email_zustimmung: '' | 'mit' | 'ohne'
  /** Eigentumsverhältnis-Id → Ausnahme. */
  ausnahmen: Record<string, Ausnahme>
}

export const LEERE_AUSWAHL: EmpfaengerAuswahl = { einheit_typ: [], email_zustimmung: '', ausnahmen: {} }

/** Baut den `empfaenger_filter` des Backends (Spec 7.4, Serienlauf-Service); leere Angaben entfallen. */
export function filterAufbauen(auswahl: EmpfaengerAuswahl): SerienlaufFilter {
  const ids = (art: Ausnahme) => Object.entries(auswahl.ausnahmen).filter(([, a]) => a === art).map(([id]) => id).sort()
  const filter: SerienlaufFilter = {}
  if (auswahl.einheit_typ.length > 0) filter.einheit_typ = [...auswahl.einheit_typ]
  if (auswahl.email_zustimmung) filter.email_zustimmung = auswahl.email_zustimmung
  const aus = ids('aus')
  const zu = ids('zu')
  if (aus.length > 0) filter.ausschliessen = aus
  if (zu.length > 0) filter.hinzufuegen = zu
  return filter
}

export function filterBeschreibung(auswahl: EmpfaengerAuswahl): string {
  const teile = ['Alle aktiven Eigentümer']
  if (auswahl.einheit_typ.length > 0) teile.push(`Einheitstyp: ${auswahl.einheit_typ.join(', ')}`)
  if (auswahl.email_zustimmung === 'mit') teile.push('nur mit E-Mail-Zustimmung')
  if (auswahl.email_zustimmung === 'ohne') teile.push('nur ohne E-Mail-Zustimmung')
  const aus = Object.values(auswahl.ausnahmen).filter(a => a === 'aus').length
  const zu = Object.values(auswahl.ausnahmen).filter(a => a === 'zu').length
  if (aus > 0) teile.push(`${aus} abgewählt`)
  if (zu > 0) teile.push(`${zu} zusätzlich`)
  return teile.join(' · ')
}
