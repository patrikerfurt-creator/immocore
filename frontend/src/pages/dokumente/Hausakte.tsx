import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { aktenApi } from '../../api/akten'
import { objekteApi } from '../../api/objekte'
import Aktenansicht from '../../components/akten/Aktenansicht'

/**
 * Hausakte eines Objekts. Die eigentliche Darstellung (Registerbaum +
 * Dokumente + Einsortieren) steckt in <Aktenansicht>, die sich Haus-,
 * Wohnungs- und Eigentümerakte teilen. Diese Seite liefert nur die
 * Objektauswahl und lädt die Akte.
 */
export default function Hausakte() {
  const qc = useQueryClient()
  const [suchParams, setSuchParams] = useSearchParams()
  const objektId = suchParams.get('objekt') ?? ''

  const { data: objekte = [] } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })

  const { data: akte, isLoading, isError } = useQuery({
    queryKey: ['hausakte', objektId],
    queryFn: () => aktenApi.hausakte(objektId),
    enabled: Boolean(objektId),
  })

  const neuLaden = () => qc.invalidateQueries({ queryKey: ['hausakte', objektId] })

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Hausakte</h1>
          {akte && (
            <span className="text-sm text-gray-500">
              {akte.anzahl_dokumente} Dokument{akte.anzahl_dokumente === 1 ? '' : 'e'}
            </span>
          )}
        </div>
        <select
          className="border rounded px-2 py-1 text-sm min-w-72"
          value={objektId}
          onChange={e => setSuchParams(e.target.value ? { objekt: e.target.value } : {})}
        >
          <option value="">Objekt wählen…</option>
          {objekte.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
          ))}
        </select>
      </div>

      {!objektId && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            Bitte oben rechts ein Objekt wählen.
          </p>
        </div>
      )}

      {objektId && isLoading && (
        <p className="text-sm text-gray-500">Akte wird geladen…</p>
      )}
      {objektId && isError && (
        <p className="text-sm text-red-700">Die Akte konnte nicht geladen werden.</p>
      )}

      {akte && (
        <Aktenansicht
          akte={akte}
          aktenart="haus"
          objektId={objektId}
          kontextKey={objektId}
          onReload={neuLaden}
        />
      )}
    </div>
  )
}
