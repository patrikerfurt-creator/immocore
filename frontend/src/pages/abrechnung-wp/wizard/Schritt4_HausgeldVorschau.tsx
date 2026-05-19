import { useQuery } from '@tanstack/react-query'
import { wirtschaftsplanApi, type Wirtschaftsplan, type VorschauPosition } from '../../../api/wirtschaftsplan'

interface Props {
  wp: Wirtschaftsplan
  onWeiter: () => void
  onZurueck: () => void
}

export function Schritt4_HausgeldVorschau({ wp, onWeiter, onZurueck }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['wp-vorschau', wp.id],
    queryFn: () => wirtschaftsplanApi.vorschauHausgeld(wp.id),
    staleTime: 30_000,
  })

  const positionen = data?.positionen ?? []
  const basKeys = positionen.length > 0
    ? Object.keys(positionen[0].bas).sort()
    : []

  const gesamtSumme = positionen.reduce((s: number, p: VorschauPosition) => s + parseFloat(p.summe), 0)

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-800 mb-1">Hausgeld-Vorschau</h2>
      <p className="text-sm text-gray-500 mb-4">
        Erwartetes monatliches Hausgeld je Einheit nach Beschluss dieses Wirtschaftsplans.
      </p>

      {isLoading && <p className="text-sm text-gray-400">Lade Vorschau…</p>}
      {isError && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-600 mb-4">
          Vorschau konnte nicht geladen werden.
        </div>
      )}

      {!isLoading && !isError && positionen.length === 0 && (
        <p className="text-sm text-gray-400 mb-4">Keine Einheiten mit aktivem Eigentumsverhältnis gefunden.</p>
      )}

      {positionen.length > 0 && (
        <div className="rounded-lg border border-gray-200 overflow-hidden mb-6 overflow-x-auto">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-16">Einheit</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Lage</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Eigentümer</th>
                {basKeys.map(ba => (
                  <th key={ba} className="text-right px-4 py-2.5 font-medium text-gray-600">BA {ba}</th>
                ))}
                <th className="text-right px-4 py-2.5 font-medium text-gray-700">Gesamt/Monat</th>
              </tr>
            </thead>
            <tbody>
              {positionen.map((pos: VorschauPosition) => (
                <tr key={pos.ev_id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono text-gray-500 text-xs">{pos.einheit_nr}</td>
                  <td className="px-4 py-2.5 text-gray-600">{pos.lage}</td>
                  <td className="px-4 py-2.5 text-gray-700">{pos.person_name}</td>
                  {basKeys.map(ba => (
                    <td key={ba} className="px-4 py-2.5 text-right text-gray-600">
                      {pos.bas[ba]
                        ? parseFloat(pos.bas[ba]).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
                        : '–'}
                    </td>
                  ))}
                  <td className="px-4 py-2.5 text-right font-semibold text-primary-700">
                    {parseFloat(pos.summe).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 border-t border-gray-200">
              <tr>
                <td colSpan={3 + basKeys.length} className="px-4 py-2.5 font-medium text-gray-700">
                  Gesamt monatlich
                </td>
                <td className="px-4 py-2.5 text-right font-bold text-gray-900">
                  {gesamtSumme.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onZurueck} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
          ← Zurück
        </button>
        <button
          onClick={onWeiter}
          className="bg-primary-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-primary-700"
        >
          Weiter →
        </button>
      </div>
    </div>
  )
}
