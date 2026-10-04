import type { Eingabefeld, Schreiben, SchreibenKanal, SchreibenStatus, VorlagenAnlass } from '../../../types'

export const SCHREIBEN_STATUS_LABEL: Record<SchreibenStatus, string> = {
  entwurf: 'Entwurf',
  zur_pruefung: 'Zur Prüfung',
  freigegeben: 'Freigegeben',
  versendet: 'Versendet',
  versand_fehlgeschlagen: 'Versand fehlgeschlagen',
  verworfen: 'Verworfen',
}

/** Anzeige-Status eines Schreibens: `entwurf` mit Fehler heißt im Postausgang „nicht erzeugbar“. */
export type SchreibenAnzeigeStatus = SchreibenStatus | 'nicht_erzeugbar'

export function anzeigeStatus(s: Pick<Schreiben, 'status' | 'nicht_erzeugbar' | 'fehler'>): SchreibenAnzeigeStatus {
  return s.nicht_erzeugbar || (s.status === 'entwurf' && !!s.fehler) ? 'nicht_erzeugbar' : s.status
}

export const ANZEIGE_STATUS_LABEL: Record<SchreibenAnzeigeStatus, string> = {
  ...SCHREIBEN_STATUS_LABEL,
  nicht_erzeugbar: 'Nicht erzeugbar',
}

/** Farbvariante der wiederverwendeten `Badge`-Komponente je Anzeige-Status. */
export const ANZEIGE_STATUS_BADGE: Record<SchreibenAnzeigeStatus, string> = {
  entwurf: 'entwurf',
  zur_pruefung: 'in_pruefung',
  freigegeben: 'freigegeben',
  versendet: 'versendet',
  versand_fehlgeschlagen: 'fehlgeschlagen',
  verworfen: 'verworfen',
  nicht_erzeugbar: 'unklar',
}

/** Filter „Ansicht“ im Postausgang → Wert für `?status=` (leer = Standard-Postausgang). */
export const POSTAUSGANG_ANSICHTEN: Array<{ value: string; label: string }> = [
  { value: '', label: 'Alle offenen' },
  { value: 'zur_pruefung', label: 'Zur Prüfung' },
  { value: 'nicht_erzeugbar', label: 'Nicht erzeugbar' },
  { value: 'versand_fehlgeschlagen', label: 'Versand fehlgeschlagen' },
]

/** Kanalwahl beim Erstellen: leer = Standard laut Vorlage und Zustellweg der Person. */
export const KANAL_WAHL: Array<{ value: '' | SchreibenKanal; label: string }> = [
  { value: '', label: 'Standard (laut Vorlage und Zustellweg)' },
  { value: 'brief', label: 'Brief' },
  { value: 'email', label: 'E-Mail' },
  { value: 'beides', label: 'Brief und E-Mail' },
]

/** Mahnungen entstehen im Mahnwesen (Phase 6), nicht über „Schreiben erstellen“ und nicht als Serienbrief. */
export function istMahnAnlass(anlass: VorlagenAnlass | string): boolean {
  return anlass.startsWith('mahnung_')
}

export type EingabeWerte = Record<string, string | boolean>

/** Namen bzw. Labels der Pflicht-Eingabefelder, die noch leer sind (Ja/Nein-Felder gelten immer als beantwortet). */
export function fehlendePflichtfelder(felder: Eingabefeld[], werte: EingabeWerte): string[] {
  return felder
    .filter(f => f.name && f.pflicht && f.typ !== 'ja_nein')
    .filter(f => {
      const w = werte[f.name]
      return typeof w !== 'string' || w.trim() === ''
    })
    .map(f => f.label || f.name)
}

export function datumZeit(iso: string | null | undefined): string {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`
}
