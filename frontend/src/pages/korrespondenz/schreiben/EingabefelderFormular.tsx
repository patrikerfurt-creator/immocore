import type { Eingabefeld } from '../../../types'
import type { EingabeWerte } from './schreibenKonstanten'

interface Props {
  felder: Eingabefeld[]
  werte: EingabeWerte
  onChange: (werte: EingabeWerte) => void
  legende?: string
}

/**
 * Formular für die Eingabefelder einer Vorlagenversion (Spec 3.5). Die Werte werden vor dem
 * Senden mit `eingabewerteAufbereiten` (aus dem Editor) ins Backend-Format gebracht.
 */
export function EingabefelderFormular({ felder, werte, onChange, legende = 'Angaben für das Schreiben' }: Props) {
  const sichtbar = felder.filter(f => f.name)
  if (sichtbar.length === 0) return null
  const setze = (name: string, wert: string | boolean) => onChange({ ...werte, [name]: wert })

  return (
    <fieldset className="border border-gray-200 rounded p-3 space-y-3">
      <legend className="text-xs text-gray-500 px-1">{legende}</legend>
      {sichtbar.map(f => (
        <label key={f.name} className="block text-sm">
          <span className="text-gray-700">{f.label || f.name}{f.pflicht ? ' *' : ''}</span>
          {f.typ === 'ja_nein' ? (
            <input type="checkbox" className="ml-2"
              checked={werte[f.name] === true}
              onChange={e => setze(f.name, e.target.checked)} />
          ) : f.typ === 'mehrzeilig' || f.typ === 'liste' ? (
            <textarea rows={3} value={(werte[f.name] as string) ?? ''}
              placeholder={f.typ === 'liste' ? 'Ein Eintrag pro Zeile' : ''}
              onChange={e => setze(f.name, e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1" />
          ) : (
            <input
              type={f.typ === 'datum' ? 'date' : f.typ === 'uhrzeit' ? 'time' : 'text'}
              value={(werte[f.name] as string) ?? ''}
              placeholder={f.typ === 'betrag' ? '1234,56' : ''}
              onChange={e => setze(f.name, e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded px-2 py-1" />
          )}
        </label>
      ))}
    </fieldset>
  )
}
