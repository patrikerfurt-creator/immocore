import type { HandwerkerauftragEreignisTyp, HandwerkerauftragStatus } from '../../types'

// Klartext-Labels für die Handwerkerauftrags-Stati (Muster: VorgangDetail STATUS_LABEL).
export const HWA_STATUS_LABEL: Record<HandwerkerauftragStatus, string> = {
  entwurf:       'Entwurf',
  versendet:     'Versendet',
  angenommen:    'Angenommen',
  abgelehnt:     'Abgelehnt',
  in_arbeit:     'In Arbeit',
  abgeschlossen: 'Abgeschlossen',
  storniert:     'Storniert',
  abgelaufen:    'Abgelaufen',
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
  versendet:     ['angenommen', 'abgelehnt', 'abgelaufen', 'storniert'],
  angenommen:    ['in_arbeit', 'abgeschlossen', 'storniert'],
  in_arbeit:     ['abgeschlossen', 'storniert'],
  abgelehnt:     ['storniert'],
  abgelaufen:    ['versendet', 'storniert'],
  abgeschlossen: [],
  storniert:     [],
}

// Ziele, die ein SACHBEARBEITER per Knopf DIREKT auslösen darf (Phase-D-
// Abnahme, Fehler 1 — bewusst eine eigene, kleinere Menge als
// HWA_ERLAUBTE_UEBERGAENGE):
//
// - 'entwurf' → 'versendet' ist HIER NICHT enthalten: das würde den Auftrag
//   als versendet markieren, OHNE dass eine Mail rausgeht — das System würde
//   fälschlich behaupten, der Handwerker sei beauftragt. Die fachlich
//   richtige Aktion aus 'entwurf' ist der Versand-Knopf (siehe
//   HandwerkerauftragDetail — löst 'erneut-versenden' aus, das den Auftrag
//   NACH erfolgreichem Mailversand automatisch auf 'versendet' setzt).
// - 'abgelaufen' → 'versendet' ist HIER NICHT enthalten: ein reiner
//   Statuswechsel ohne neuen Bestätigungs-Token — die Links des Handwerkers
//   blieben tot, der Status würde aber 'versendet' lügen. Auch hier ist der
//   Versand-Knopf die richtige Aktion.
// - 'versendet' → 'abgelaufen' ist HIER NICHT enthalten: 'abgelaufen' ist ein
//   reiner SYSTEM-Status, den ausschließlich der Nachtlauf
//   (pruefe_abgelaufene_auftraege) anhand der Token-Frist setzt — als
//   manueller Knopf wäre er sinnlos und irreführend.
export const HWA_MANUELLE_UEBERGAENGE: Record<HandwerkerauftragStatus, HandwerkerauftragStatus[]> = {
  entwurf:       ['storniert'],
  versendet:     ['angenommen', 'abgelehnt', 'storniert'],
  angenommen:    ['in_arbeit', 'abgeschlossen', 'storniert'],
  in_arbeit:     ['abgeschlossen', 'storniert'],
  abgelehnt:     ['storniert'],
  abgelaufen:    ['storniert'],
  abgeschlossen: [],
  storniert:     [],
}

export const HWA_EREIGNIS_LABEL: Record<HandwerkerauftragEreignisTyp, string> = {
  statuswechsel:          'Statuswechsel',
  versand:                'Versand',
  versand_fehlgeschlagen: 'Versand fehlgeschlagen',
  kommentar:              'Kommentar',
  rechnung_zugeordnet:    'Rechnung zugeordnet',
  system_abgelaufen:      'System: Auftrag abgelaufen',
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
