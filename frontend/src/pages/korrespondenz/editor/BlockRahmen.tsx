import type { Editor } from '@tiptap/react'
import type { Platzhalter, Textbaustein, VorlagenBlock } from '../../../types'
import { BlockTextEditor } from './BlockTextEditor'
import type { PlatzhalterVorschlag } from './BlockTextEditor'
import { BLOCK_LABEL, TABELLEN_QUELLEN, hatTextKoerper } from './blockModell'

interface Props {
  index: number
  anzahl: number
  block: VorlagenBlock
  readOnly: boolean
  bausteine: Textbaustein[]
  /** Alle bekannten Platzhalter (Registry + Eingabefelder) — für Autovervollständigung und Datalists. */
  platzhalter: Platzhalter[]
  kiVerfuegbar: boolean
  onAendern: (block: VorlagenBlock) => void
  onVerschieben: (richtung: -1 | 1) => void
  onEntfernen: () => void
  onKiUeberarbeiten: () => void
  onFokus: (editor: Editor) => void
}

const RAHMEN_FARBE: Record<VorlagenBlock['typ'], string> = {
  text: 'border-gray-300',
  baustein: 'border-teal-300',
  tabelle: 'border-indigo-300',
  liste: 'border-purple-300',
  bedingt: 'border-amber-300',
  seitenumbruch: 'border-dashed border-gray-400',
  anlage_seite: 'border-rose-300',
}

const feld = 'w-full border border-gray-300 rounded px-2 py-1.5 text-sm disabled:bg-gray-50'

/** Rahmen um einen Block: Typ-Kopf mit Aktionen + typspezifischer Körper. */
export function BlockRahmen({
  index, anzahl, block, readOnly, bausteine, platzhalter, kiVerfuegbar,
  onAendern, onVerschieben, onEntfernen, onKiUeberarbeiten, onFokus,
}: Props) {
  const vorschlaege: PlatzhalterVorschlag[] = platzhalter
  const listenId = `dl-${block.typ}-${index}`
  const optionen = (filter: (p: Platzhalter) => boolean, extra: string[] = []) =>
    [...new Set([...extra, ...platzhalter.filter(filter).map(p => p.name)])]

  return (
    <section
      className={`bg-white border-l-4 border border-gray-200 rounded-lg ${RAHMEN_FARBE[block.typ]}`}
      aria-label={`Block ${index + 1}: ${BLOCK_LABEL[block.typ]}`}
    >
      <header className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border-b border-gray-200 rounded-t-lg">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">
          {index + 1}. {BLOCK_LABEL[block.typ]}
        </span>
        <span className="ml-auto flex items-center gap-1">
          {!readOnly && kiVerfuegbar && hatTextKoerper(block) && (
            <button type="button" onClick={onKiUeberarbeiten}
              className="text-xs rounded border border-primary-300 text-primary-700 px-2 py-0.5 hover:bg-primary-50">
              ✨ Mit KI überarbeiten
            </button>
          )}
          {!readOnly && (
            <>
              <button type="button" aria-label={`Block ${index + 1} nach oben`} disabled={index === 0}
                onClick={() => onVerschieben(-1)}
                className="px-1.5 text-gray-500 hover:text-gray-900 disabled:opacity-30">↑</button>
              <button type="button" aria-label={`Block ${index + 1} nach unten`} disabled={index === anzahl - 1}
                onClick={() => onVerschieben(1)}
                className="px-1.5 text-gray-500 hover:text-gray-900 disabled:opacity-30">↓</button>
              <button type="button" aria-label={`Block ${index + 1} entfernen`} onClick={onEntfernen}
                className="px-1.5 text-red-500 hover:text-red-800">✕</button>
            </>
          )}
        </span>
      </header>

      <div className="p-3 space-y-2">
        {block.typ === 'text' && (
          <BlockTextEditor label={`Text Block ${index + 1}`} inhalt={block.inhalt} platzhalter={vorschlaege}
            readOnly={readOnly} onFokus={onFokus}
            onChange={inhalt => onAendern({ ...block, inhalt })} />
        )}

        {block.typ === 'bedingt' && (
          <>
            <label className="block text-sm">
              <span className="text-gray-700">Bedingung (Text erscheint nur, wenn erfüllt)</span>
              <input className={`${feld} font-mono mt-1`} list={listenId} value={block.bedingung} disabled={readOnly}
                placeholder="z. B. ev.sepa_mandat_fehlt"
                onChange={e => onAendern({ ...block, bedingung: e.target.value })} />
              <datalist id={listenId}>
                {optionen(p => p.typ === 'bool').map(n => <option key={n} value={n} />)}
              </datalist>
            </label>
            <BlockTextEditor label={`Bedingter Text Block ${index + 1}`} inhalt={block.inhalt}
              platzhalter={vorschlaege} readOnly={readOnly} onFokus={onFokus}
              onChange={inhalt => onAendern({ ...block, inhalt })} />
          </>
        )}

        {block.typ === 'anlage_seite' && (
          <>
            <label className="block text-sm">
              <span className="text-gray-700">Titel der Anlageseite</span>
              <input className={`${feld} mt-1`} value={block.titel} disabled={readOnly}
                placeholder="z. B. Vertretungsvollmacht"
                onChange={e => onAendern({ ...block, titel: e.target.value })} />
            </label>
            <p className="text-xs text-gray-500">Eigene Folgeseite ohne Briefkopf, mit Fußzeile.</p>
            <BlockTextEditor label={`Anlageseite Block ${index + 1}`} inhalt={block.inhalt}
              platzhalter={vorschlaege} readOnly={readOnly} onFokus={onFokus}
              onChange={inhalt => onAendern({ ...block, inhalt })} />
          </>
        )}

        {block.typ === 'baustein' && (
          <label className="block text-sm">
            <span className="text-gray-700">Textbaustein</span>
            <select className={`${feld} mt-1`} value={block.code} disabled={readOnly}
              onChange={e => onAendern({ ...block, code: e.target.value })}>
              <option value="">— wählen —</option>
              {!bausteine.some(b => b.code === block.code) && block.code && (
                <option value={block.code}>{block.code} (nicht gefunden)</option>
              )}
              {bausteine.map(b => (
                <option key={b.id} value={b.code}>{b.code} — {b.bezeichnung}</option>
              ))}
            </select>
            {bausteine.find(b => b.code === block.code)?.inhalt && (
              <p className="mt-1 text-xs text-gray-500 whitespace-pre-wrap border-l-2 border-teal-200 pl-2">
                {bausteine.find(b => b.code === block.code)!.inhalt}
              </p>
            )}
          </label>
        )}

        {block.typ === 'tabelle' && (
          <label className="block text-sm">
            <span className="text-gray-700">Datenquelle der Tabelle</span>
            <input className={`${feld} font-mono mt-1`} list={listenId} value={block.quelle} disabled={readOnly}
              placeholder="z. B. mahnung.offene_posten"
              onChange={e => onAendern({ ...block, quelle: e.target.value })} />
            <datalist id={listenId}>
              {optionen(p => p.typ === 'tabelle', TABELLEN_QUELLEN).map(n => <option key={n} value={n} />)}
            </datalist>
          </label>
        )}

        {block.typ === 'liste' && (
          <label className="block text-sm">
            <span className="text-gray-700">Quelle der Liste (Eingabefeld vom Typ „Liste“)</span>
            <input className={`${feld} font-mono mt-1`} list={listenId} value={block.quelle} disabled={readOnly}
              placeholder="z. B. eingabe.tagesordnung"
              onChange={e => onAendern({ ...block, quelle: e.target.value })} />
            <datalist id={listenId}>
              {optionen(p => p.typ === 'liste').map(n => <option key={n} value={n} />)}
            </datalist>
          </label>
        )}

        {block.typ === 'seitenumbruch' && (
          <p className="text-sm text-gray-500 text-center">— Ab hier beginnt eine neue Seite —</p>
        )}
      </div>
    </section>
  )
}
