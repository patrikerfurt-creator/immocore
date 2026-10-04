import { Button } from '../../../components/ui/Button'
import type { Eingabefeld } from '../../../types'
import { EINGABEFELD_NAME, EINGABEFELD_TYPEN } from './blockModell'

interface Props {
  felder: Eingabefeld[]
  onChange: (felder: Eingabefeld[]) => void
  readOnly?: boolean
}

/** Definiert die Eingabefelder einer Version (Spec 3.5): Name, Label, Typ, Pflicht. */
export function EingabefeldDesigner({ felder, onChange, readOnly = false }: Props) {
  function aendern(index: number, teil: Partial<Eingabefeld>) {
    onChange(felder.map((f, i) => (i === index ? { ...f, ...teil } : f)))
  }

  const doppelt = (name: string) => name !== '' && felder.filter(f => f.name === name).length > 1

  return (
    <section className="bg-white border border-gray-200 rounded-lg p-4" aria-label="Eingabefelder">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-800">Eingabefelder</h3>
        {!readOnly && (
          <Button
            size="sm" variant="secondary" type="button"
            onClick={() => onChange([...felder, { name: '', label: '', typ: 'text', pflicht: false }])}
          >
            + Feld
          </Button>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-3">
        Werte, die je Schreiben bzw. Serienlauf einmal eingegeben werden. Im Text als{' '}
        <code>{'{{ eingabe.name }}'}</code>.
      </p>
      {felder.length === 0 && <p className="text-sm text-gray-400">Keine Eingabefelder definiert.</p>}
      <div className="space-y-2">
        {felder.map((f, i) => {
          const nameUngueltig = f.name !== '' && !EINGABEFELD_NAME.test(f.name)
          return (
            <div key={i} className="grid grid-cols-12 gap-2 items-start">
              <div className="col-span-3">
                <input
                  aria-label={`Feldname ${i + 1}`}
                  value={f.name}
                  disabled={readOnly}
                  onChange={e => aendern(i, { name: e.target.value })}
                  placeholder="name (z. B. versammlung_ort)"
                  className={`w-full border rounded px-2 py-1 text-sm font-mono ${nameUngueltig || doppelt(f.name) ? 'border-red-400' : 'border-gray-300'}`}
                />
                {nameUngueltig && (
                  <p className="text-xs text-red-600 mt-0.5">Nur a–z, 0–9 und _; beginnt mit Buchstabe.</p>
                )}
                {doppelt(f.name) && <p className="text-xs text-red-600 mt-0.5">Name doppelt vergeben.</p>}
              </div>
              <input
                aria-label={`Label ${i + 1}`}
                value={f.label}
                disabled={readOnly}
                onChange={e => aendern(i, { label: e.target.value })}
                placeholder="Bezeichnung für den Anwender"
                className="col-span-4 border border-gray-300 rounded px-2 py-1 text-sm"
              />
              <select
                aria-label={`Typ ${i + 1}`}
                value={f.typ}
                disabled={readOnly}
                onChange={e => aendern(i, { typ: e.target.value as Eingabefeld['typ'] })}
                className="col-span-3 border border-gray-300 rounded px-2 py-1 text-sm"
              >
                {EINGABEFELD_TYPEN.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <label className="col-span-1 flex items-center gap-1 text-sm pt-1">
                <input
                  type="checkbox"
                  checked={f.pflicht}
                  disabled={readOnly}
                  onChange={e => aendern(i, { pflicht: e.target.checked })}
                />
                Pflicht
              </label>
              {!readOnly && (
                <button
                  type="button"
                  aria-label={`Feld ${i + 1} entfernen`}
                  className="col-span-1 text-red-600 hover:text-red-800 text-sm pt-1"
                  onClick={() => onChange(felder.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
