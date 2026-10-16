import type { HandwerkerauftragEreignisTyp, HandwerkerauftragStatus } from '../../types'

// Klartext-Labels für die Handwerkerauftrags-Stati (Muster: VorgangDetail STATUS_LABEL).
export const HWA_STATUS_LABEL: Record<HandwerkerauftragStatus, string> = {
  entwurf:       'Entwurf',
  versendet:     'Versendet',
  in_arbeit:     'In Arbeit',
  abgeschlossen: 'Abgeschlossen',
  storniert:     'Storniert',
}

export const HWA_STATUS_OPTIONEN: { value: HandwerkerauftragStatus; label: string }[] =
  (Object.keys(HWA_STATUS_LABEL) as HandwerkerauftragStatus[]).map(v => ({ value: v, label: HWA_STATUS_LABEL[v] }))

// Spiegel von apps.handwerker.services.auftrag_service._ERLAUBTE_UEBERGAENGE
// (das Backend liefert keinen eigenen Endpunkt dafür — analog VorgangDetail).
// ACHTUNG: das ist die Tabelle des SERVICE (was der Service technisch zulässt),
// NICHT die Liste der Knöpfe im UI — dafür siehe HWA_MANUELLE_UEBERGAENGE
// weiter unten. Diese Tabelle bewusst unverändert lassen.
export const HWA_ERLAUBTE_UEBERGAENGE: Record<HandwerkerauftragStatus, HandwerkerauftragStatus[]> = {
  entwurf:       ['versendet', 'storniert'],
  versendet:     ['in_arbeit', 'storniert'],
  in_arbeit:     ['abgeschlossen', 'storniert'],
  abgeschlossen: [],
  storniert:     [],
}

// Ziele, die ein SACHBEARBEITER per Knopf DIREKT auslösen darf (bewusst eine
// eigene Menge neben HWA_ERLAUBTE_UEBERGAENGE):
//
// - 'entwurf' → 'versendet' ist HIER NICHT enthalten: das würde den Auftrag
//   als versendet markieren, OHNE dass eine Mail rausgeht — das System würde
//   fälschlich behaupten, der Handwerker sei beauftragt. Die fachlich
//   richtige Aktion aus 'entwurf' ist der Versand-Knopf (siehe
//   HandwerkerauftragDetail — löst 'erneut-versenden' aus, das den Auftrag
//   NACH erfolgreichem Mailversand automatisch auf 'versendet' setzt).
// - Es gibt keine Auftragsbestätigung per Link mehr: der Handwerker antwortet
//   formlos per Mail, 'in_arbeit' setzt der Sachbearbeiter manuell.
export const HWA_MANUELLE_UEBERGAENGE: Record<HandwerkerauftragStatus, HandwerkerauftragStatus[]> = {
  entwurf:       ['storniert'],
  versendet:     ['in_arbeit', 'storniert'],
  in_arbeit:     ['abgeschlossen', 'storniert'],
  abgeschlossen: [],
  storniert:     [],
}

export const HWA_EREIGNIS_LABEL: Record<HandwerkerauftragEreignisTyp, string> = {
  statuswechsel:          'Statuswechsel',
  versand:                'Versand',
  versand_fehlgeschlagen: 'Versand fehlgeschlagen',
  kommentar:              'Kommentar',
  rechnung_zugeordnet:    'Rechnung zugeordnet',
}

// Freundliche Fehlermeldung aus einer Axios-Fehlerantwort extrahieren
// (Backend liefert bei 400 {detail: ...} oder Feldfehler {feld: [...]}).
export function fehlerText(error: unknown, fallback: string): string {
  // @ts-expect-error axios error shape
  const data = error?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return String(data.detail)
  const werte = Object.values(data as Record<string, unknown>).flat()
  return werte.length > 0 ? werte.join(' ') : fallback
}

export function formatGeld(wert: string | null): string {
  if (wert == null) return '–'
  const n = parseFloat(wert)
  return Number.isNaN(n) ? '–' : `${n.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €`
}

export function formatDatum(s: string | null): string {
  return s ? new Date(s).toLocaleDateString('de-DE') : '–'
}

export function formatDatumZeit(s: string | null): string {
  return s ? new Date(s).toLocaleString('de-DE') : '–'
}
