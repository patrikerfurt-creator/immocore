import { useMemo, useState } from 'react'
import type { Platzhalter } from '../../../types'

interface Props {
  platzhalter: Platzhalter[]
  laedt?: boolean
  fehler?: string | null
  readOnly?: boolean
  /** Fügt den Platzhalter am Cursor des zuletzt fokussierten Feldes ein. */
  onEinfuegen: (name: string) => void
}

const GRUPPE_LABEL: Record<string, string> = {
  empfaenger: 'Empfänger', objekt: 'Objekt', einheit: 'Einheit', schreiben: 'Schreiben',
  verwaltung: 'Verwaltung', bank: 'Bank', ev: 'Eigentümer', hausgeld: 'Hausgeld',
  wechsel: 'Wechsel', mahnung: 'Mahnung', vorgang: 'Vorgang', eingabe: 'Eingabefelder',
}

/** Seitenleiste: Platzhalter je Anlass als anklickbare Chips, gruppiert und durchsuchbar. */
export function PlatzhalterSeitenleiste({ platzhalter, laedt, fehler, readOnly, onEinfuegen }: Props) {
  const [suche, setSuche] = useState('')

  const gruppen = useMemo(() => {
    const s = suche.trim().toLowerCase()
    const treffer = platzhalter.filter(p =>
      !s || p.name.toLowerCase().includes(s) || p.beschreibung.toLowerCase().includes(s))
    const map = new Map<string, Platzhalter[]>()
    for (const p of treffer) {
      const liste = map.get(p.gruppe) ?? []
      liste.push(p)
      map.set(p.gruppe, liste)
    }
    return [...map.entries()]
  }, [platzhalter, suche])

  return (
    <aside className="bg-white border border-gray-200 rounded-lg p-3 text-sm" aria-label="Platzhalter">
      <h3 className="font-semibold text-gray-800 mb-2">Platzhalter</h3>
      <input
        type="search"
        value={suche}
        onChange={e => setSuche(e.target.value)}
        placeholder="Suchen…"
        aria-label="Platzhalter suchen"
        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mb-2"
      />
      {laedt && <p className="text-gray-400">Lade Platzhalter…</p>}
      {fehler && <p className="text-red-600">{fehler}</p>}
      {!laedt && !fehler && gruppen.length === 0 && <p className="text-gray-400">Keine Platzhalter.</p>}
      <div className="space-y-3 max-h-[60vh] overflow-y-auto">
        {gruppen.map(([gruppe, liste]) => (
          <div key={gruppe}>
            <div className="text-xs font-semibold uppercase text-gray-500 mb-1">
              {GRUPPE_LABEL[gruppe] ?? gruppe}
            </div>
            <div className="flex flex-wrap gap-1">
              {liste.map(p => (
                <button
                  key={p.name}
                  type="button"
                  disabled={readOnly}
                  // Fokus im Editor behalten, damit die Einfügeposition erhalten bleibt.
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => onEinfuegen(p.name)}
                  title={`${p.beschreibung}${p.beispiel != null && p.beispiel !== '' ? ` — z. B. ${String(p.beispiel)}` : ''} (${p.typ})`}
                  className="rounded bg-blue-100 text-blue-800 hover:bg-blue-200 disabled:opacity-50 px-1.5 py-0.5 text-xs font-mono"
                >
                  {p.name.startsWith(`${gruppe}.`) ? p.name.slice(gruppe.length + 1) : p.name}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}
