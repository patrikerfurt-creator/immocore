// Reine Hilfsfunktionen des Vorlagen-Editors (keine React-/TipTap-Abhängigkeit):
// Blockmodell, Umwandlung zwischen Jinja-Quelltext und Editor-HTML, Prüfungen.
// Blockstruktur: Spec 3.4.
import type { Eingabefeld, Platzhalter, VorlagenBlock, VorlagenBlockTyp } from '../../../types'

export const BLOCK_TYPEN: VorlagenBlockTyp[] = [
  'text', 'baustein', 'tabelle', 'liste', 'bedingt', 'seitenumbruch', 'anlage_seite',
]

export const BLOCK_LABEL: Record<VorlagenBlockTyp, string> = {
  text: 'Text',
  baustein: 'Textbaustein',
  tabelle: 'Tabelle (systemerzeugt)',
  liste: 'Liste (aus Eingabefeld)',
  bedingt: 'Bedingter Text',
  seitenumbruch: 'Seitenumbruch',
  anlage_seite: 'Anlageseite',
}

/** Systemerzeugte Tabellen (Backend-Registry `TABELLEN`); freie Eingabe bleibt möglich. */
export const TABELLEN_QUELLEN = ['mahnung.offene_posten', 'hausgeld.positionen']

export const EINGABEFELD_TYPEN: Array<{ value: Eingabefeld['typ']; label: string }> = [
  { value: 'text', label: 'Text (einzeilig)' },
  { value: 'mehrzeilig', label: 'Text (mehrzeilig)' },
  { value: 'datum', label: 'Datum' },
  { value: 'uhrzeit', label: 'Uhrzeit' },
  { value: 'betrag', label: 'Betrag' },
  { value: 'liste', label: 'Liste' },
  { value: 'ja_nein', label: 'Ja / Nein' },
]

// ---- Blöcke mit lokalem Schlüssel ------------------------------------------

/** Editor-Zustand eines Blocks; `key` ist nur lokal (React-Key) und wird nie gespeichert. */
export interface BlockEintrag {
  key: string
  block: VorlagenBlock
}

let keyZaehler = 0
export function neuerKey(): string {
  keyZaehler += 1
  return `blk-${keyZaehler}`
}

export function zuEintraegen(bloecke: VorlagenBlock[] | null | undefined): BlockEintrag[] {
  return (bloecke ?? []).map(block => ({ key: neuerKey(), block }))
}

export function zuBloecken(eintraege: BlockEintrag[]): VorlagenBlock[] {
  return eintraege.map(e => e.block)
}

export function neuerBlock(typ: VorlagenBlockTyp): VorlagenBlock {
  switch (typ) {
    case 'text': return { typ, inhalt: '' }
    case 'baustein': return { typ, code: '' }
    case 'tabelle': return { typ, quelle: '' }
    case 'liste': return { typ, quelle: '' }
    case 'bedingt': return { typ, bedingung: '', inhalt: '' }
    case 'seitenumbruch': return { typ }
    case 'anlage_seite': return { typ, titel: '', inhalt: '' }
  }
}

/** Block hat einen Rich-Text-Körper (`inhalt`), der im TipTap-Editor bearbeitet wird. */
export function hatTextKoerper(block: VorlagenBlock): block is Extract<VorlagenBlock, { inhalt: string }> {
  return block.typ === 'text' || block.typ === 'bedingt' || block.typ === 'anlage_seite'
}

/** Prüft ein unbekanntes Objekt (z. B. KI-Ausgabe) auf einen gültigen Block; sonst `null`. */
export function normalisiereBlock(roh: unknown): VorlagenBlock | null {
  if (!roh || typeof roh !== 'object') return null
  const b = roh as Record<string, unknown>
  const s = (k: string) => (typeof b[k] === 'string' ? (b[k] as string) : '')
  switch (b.typ) {
    case 'text': return { typ: 'text', inhalt: s('inhalt') }
    case 'baustein': return { typ: 'baustein', code: s('code') }
    case 'tabelle': return { ...(b as object), typ: 'tabelle', quelle: s('quelle') } as VorlagenBlock
    case 'liste': return { typ: 'liste', quelle: s('quelle') }
    case 'bedingt': return { typ: 'bedingt', bedingung: s('bedingung'), inhalt: s('inhalt') }
    case 'seitenumbruch': return { typ: 'seitenumbruch' }
    case 'anlage_seite': return { typ: 'anlage_seite', titel: s('titel'), inhalt: s('inhalt') }
    default: return null
  }
}

export function normalisiereBloecke(roh: unknown): VorlagenBlock[] {
  if (!Array.isArray(roh)) return []
  return roh.map(normalisiereBlock).filter((b): b is VorlagenBlock => b !== null)
}

/** Kurzer Klartext eines Blocks für Vorschau-Listen (z. B. KI-Ergebnis). */
export function blockZusammenfassung(block: VorlagenBlock): string {
  switch (block.typ) {
    case 'text': return htmlZuText(block.inhalt)
    case 'bedingt': return `Wenn ${block.bedingung || '…'}: ${htmlZuText(block.inhalt)}`
    case 'anlage_seite': return `${block.titel || 'Anlage'} — ${htmlZuText(block.inhalt)}`
    case 'baustein': return `Baustein „${block.code}“`
    case 'tabelle': return `Tabelle: ${block.quelle}`
    case 'liste': return `Liste: ${block.quelle}`
    case 'seitenumbruch': return 'Seitenumbruch'
  }
}

function htmlZuText(html: string): string {
  return html.replace(/<\/(p|li|div|h[1-6])>/gi, '\n').replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&amp;/g, '&').trim()
}

// ---- Jinja-Quelltext <-> Editor-HTML ---------------------------------------

const BLOCK_TAG = /<\s*(p|ul|ol|li|div|table|h[1-6]|br)\b/i
const PLATZHALTER = /\{\{\s*([^{}]+?)\s*\}\}/g

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function escAttr(s: string): string {
  return escHtml(s).replace(/"/g, '&quot;')
}
function unescHtml(s: string): string {
  return s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
}

/**
 * Gespeicherter Blocktext -> HTML für TipTap. Text ohne Block-Tags gilt als
 * Absätze (Leerzeile = neuer Absatz, Zeilenumbruch = `<br>`), wie im Renderer
 * des Backends. `{{ ausdruck }}` wird zum Platzhalter-Chip.
 */
export function jinjaZuEditorHtml(quelle: string | null | undefined): string {
  const text = quelle ?? ''
  let html: string
  if (BLOCK_TAG.test(text)) {
    html = text
  } else {
    const absaetze = text.trim().split(/\n\s*\n/).map(a => a.trim()).filter(Boolean)
    html = absaetze.map(a => `<p>${escHtml(a).replace(/\n/g, '<br>')}</p>`).join('')
  }
  return html.replace(PLATZHALTER, (_m, ausdruck: string) =>
    `<span data-platzhalter="${escAttr(ausdruck)}">{{ ${escHtml(ausdruck)} }}</span>`)
}

const CHIP_SPAN = /<span\b[^>]*\bdata-platzhalter="([^"]*)"[^>]*>[\s\S]*?<\/span>/g

/** Editor-HTML (`editor.getHTML()`) -> Blocktext mit `{{ ausdruck }}`. Leerer Editor -> ''. */
export function editorHtmlZuJinja(html: string): string {
  const ohneChips = html.replace(CHIP_SPAN, (_m, ausdruck: string) => `{{ ${unescHtml(ausdruck)} }}`)
  return ohneChips.replace(/<p>(\s|<br\s*\/?>)*<\/p>/gi, '').trim() === '' ? '' : ohneChips
}

// ---- Platzhalter-Prüfung ----------------------------------------------------

/** Erster Bezeichner eines Ausdrucks: `hausgeld.betrag | euro` -> `hausgeld.betrag`. */
export function platzhalterName(ausdruck: string): string {
  return (ausdruck.match(/^[\w.]+/) ?? [''])[0]
}

/** Alle `{{ … }}`-Namen eines Quelltextes. */
export function platzhalterInText(quelle: string): string[] {
  const namen: string[] = []
  for (const m of quelle.matchAll(PLATZHALTER)) namen.push(platzhalterName(m[1]))
  return namen
}

/** Namen im Text, die weder aus der Registry noch aus den Eingabefeldern stammen. */
export function unbekanntePlatzhalter(
  quellen: string[], bekannt: Iterable<string>, eingabefelder: Eingabefeld[],
): string[] {
  const erlaubt = new Set<string>(bekannt)
  eingabefelder.forEach(f => erlaubt.add(`eingabe.${f.name}`))
  const unbekannt = new Set<string>()
  for (const q of quellen) {
    for (const name of platzhalterInText(q)) {
      if (name && !erlaubt.has(name)) unbekannt.add(name)
    }
  }
  return [...unbekannt].sort()
}

/** Alle Textquellen einer Vorlage (Betreff + Blockinhalte + Bedingungen) für die Prüfung. */
export function textQuellen(betreff: string, bloecke: VorlagenBlock[]): string[] {
  const q = [betreff]
  for (const b of bloecke) {
    if (hatTextKoerper(b)) q.push(b.inhalt)
    if (b.typ === 'bedingt') q.push(`{{ ${b.bedingung} }}`)
  }
  return q
}

/** Gültiger Eingabefeld-Name: Kleinbuchstaben/Ziffern/Unterstrich, nicht mit Ziffer beginnend. */
export const EINGABEFELD_NAME = /^[a-z][a-z0-9_]*$/

const EINGABE_TYP_ALS_PLATZHALTER: Record<Eingabefeld['typ'], string> = {
  text: 'text', mehrzeilig: 'text', uhrzeit: 'text', datum: 'datum',
  betrag: 'betrag', liste: 'liste', ja_nein: 'bool',
}

/**
 * Die dynamische Gruppe `eingabe` liefert die Registry nur mit den Eingabefeldern
 * der Version (Spec 4.2). Der Editor ergänzt sie lokal aus dem Eingabefeld-Designer.
 */
export function eingabefelderAlsPlatzhalter(felder: Eingabefeld[]): Platzhalter[] {
  return felder
    .filter(f => EINGABEFELD_NAME.test(f.name))
    .map(f => ({
      name: `eingabe.${f.name}`,
      beschreibung: f.label || f.name,
      typ: EINGABE_TYP_ALS_PLATZHALTER[f.typ] ?? 'text',
      beispiel: null,
      gruppe: 'eingabe',
    }))
}
