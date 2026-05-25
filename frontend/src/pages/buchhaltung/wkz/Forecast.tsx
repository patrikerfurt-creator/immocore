import { useQuery } from '@tanstack/react-query'
import { wkzApi, type WKZForecastPosition } from '../../../api/wkz'
import { useObjektStore } from '../../../stores/objekt'
import { Link } from 'react-router-dom'

const EUR = (v: string | number) =>
  Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')

// Gruppiert Positionen nach Datum
function gruppiereNachDatum(positionen: WKZForecastPosition[]): Map<string, WKZForecastPosition[]> {
  const map = new Map<string, WKZForecastPosition[]>()
  for (const p of positionen) {
    if (!map.has(p.faellig_am)) map.set(p.faellig_am, [])
    map.get(p.faellig_am)!.push(p)
  }
  return map
}

export default function Forecast() {
  const { selectedId: objektId } = useObjektStore()

  const { data: positionen = [], isLoading, error } = useQuery({
    queryKey: ['wkz-forecast', objektId],
    queryFn: () => wkzApi.objektForecast(objektId!),
    enabled: !!objektId,
  })

  if (!objektId) {
    return <p className="text-gray-500 p-4">Bitte ein Objekt auswählen.</p>
  }

  if (isLoading) return <p className="p-4 text-gray-400">Lade Forecast…</p>
  if (error) return <p className="p-4 text-red-600">Fehler beim Laden.</p>

  const gruppen = gruppiereNachDatum(positionen)
  const gesamtSumme = positionen.reduce((s, p) => s + Number(p.betrag), 0)

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Liquiditäts-Vorschau (90 Tage)</h1>
        <Link
          to="../wkz-vorlagen"
          className="text-sm text-blue-600 hover:underline"
        >
          Alle Vorlagen
        </Link>
      </div>

      {positionen.length === 0 ? (
        <p className="text-gray-400">
          Keine fälligen Zahlung in den nächsten 90 Tagen.
        </p>
      ) : (
        <>
          {/* Summen-Karte */}
          <div className="bg-blue-50 rounded-lg p-4 flex justify-between items-center">
            <span className="text-sm text-blue-700">
              {positionen.length} Zahlung{positionen.length !== 1 ? 'en' : ''} in 90 Tagen
            </span>
            <span className="text-lg font-semibold text-blue-900">
              {EUR(gesamtSumme)}
            </span>
          </div>

          {/* Tabelle gruppiert nach Datum */}
          <div className="space-y-4">
            {Array.from(gruppen.entries()).map(([datum, items]) => {
              const tagSumme = items.reduce((s, p) => s + Number(p.betrag), 0)
              return (
                <div key={datum} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div className="bg-gray-50 px-4 py-2 flex justify-between items-center">
                    <span className="font-medium text-sm text-gray-700">
                      {DATUM(datum)}
                    </span>
                    <span className="text-sm font-medium text-gray-600">
                      {EUR(tagSumme)}
                    </span>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {items.map((p, i) => (
                      <div
                        key={i}
                        className="px-4 py-3 flex items-center justify-between text-sm"
                      >
                        <div>
                          <Link
                            to={`../wkz-vorlagen/${p.vorlage_id}`}
                            className="text-blue-600 hover:underline font-medium"
                          >
                            {p.bezeichnung}
                          </Link>
                          <p className="text-xs text-gray-500">{p.kreditor}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-medium tabular-nums">{EUR(p.betrag)}</p>
                          <p className="text-xs text-gray-400">
                            {DATUM(p.periode_von)}–{DATUM(p.periode_bis)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
