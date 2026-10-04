// Gemeinsame Testdaten für die Oberflächen von Phase 5c (Schreiben, Druckstapel, Serienbrief).
import userEvent from '@testing-library/user-event'
import type { Schreiben, SchreibenDetail } from '../../../types'

/** Füllt ein Feld in einem Rutsch (paste statt Tastenanschlägen) — schont die Test-CPU im Container. */
export async function fuelle(feld: HTMLElement, text: string) {
  await userEvent.click(feld)
  await userEvent.paste(text)
}

export function schreibenMuster(teil: Partial<Schreiben> = {}): Schreiben {
  return {
    id: 's1', nummer: 'KS-2026-000001', status: 'zur_pruefung', status_anzeige: 'Zur Prüfung',
    nicht_erzeugbar: false, fehler: '', kanal: 'brief', auch_brief: true, betreff: 'Einladung ETV',
    vorlage: { id: 'v1', code: 'etv_einladung', bezeichnung: 'ETV-Einladung', anlass: 'etv_einladung' },
    einzeln_bearbeitbar: false,
    empfaenger: { id: 'p1', name: 'Max Muster' },
    objekt: { id: 'o1', bezeichnung: 'Musterstraße 1' },
    einheit: { id: 'e1', einheit_nr: '12' },
    serienlauf: null, vorgang: null, dokument: null, druckstapel: null,
    erstellt_am: '2026-09-28T10:00:00Z', freigegeben_am: null, versendet_am: null,
    ...teil,
  }
}

export function detailMuster(teil: Partial<SchreibenDetail> = {}): SchreibenDetail {
  return {
    ...schreibenMuster(),
    html_gerendert: '<p>Text</p>', inhalt_angepasst: null, eingabewerte: {}, ihr_zeichen: '',
    ihr_schreiben_vom: null, unterzeichner: 1, mail_message_id: '', freigegeben_von: null,
    ...teil,
  }
}
