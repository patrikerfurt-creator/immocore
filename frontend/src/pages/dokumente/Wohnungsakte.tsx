import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { aktenApi } from '../../api/akten'
import { objekteApi } from '../../api/objekte'
import Aktenansicht from '../../components/akten/Aktenansicht'

/**
 * Wohnungsakte einer Einheit. Erst ein Objekt wählen, dann eine seiner
 * Einheiten; die Darstellung teilt sie sich mit der Hausakte (<Aktenansicht>).
 * Der Objektbezug wird an die Ansicht durchgereicht, damit Registervorschlag
 * und Untergliederung auf die richtige Objektgliederung zugreifen.
 */
export default function Wohnungsakte() {
  const qc = useQueryClient()
  const [suchParams, setSuchParams] = useSearchParams()
  const objektId = suchParams.get('objekt') ?? ''
  const einheitId = suchParams.get('einheit') ?? ''

  const { data: objekte = [] } = useQuery({
    queryKey: ['objekte'],
    queryFn: () => objekteApi.list(),
  })

  const { data: einheiten = [] } = useQuery({
    queryKey: ['einheiten', objektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: objektId }),
    enabled: Boolean(objektId),
  })

  const { data: akte, isLoading, isError } = useQuery({
    queryKey: ['wohnungsakte', einheitId],
    queryFn: () => aktenApi.wohnungsakte(einheitId),
    enabled: Boolean(einheitId),
  })

  const neuLaden = () => qc.invalidateQueries({ queryKey: ['wohnungsakte', einheitId] })

  // Objektwechsel verwirft die Einheitenwahl — eine Einheit des alten Objekts
  // gehört nicht zum neuen.
  const waehleObjekt = (id: string) =>
    setSuchParams(id ? { objekt: id } : {})
  const waehleEinheit = (id: string) =>
    setSuchParams(id ? { objekt: objektId, einheit: id } : { objekt: objektId })

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Wohnungsakte</h1>
          {akte && (
            <span className="text-sm text-gray-500">
              {akte.anzahl_dokumente} Dokument{akte.anzahl_dokumente === 1 ? '' : 'e'}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <select
            className="border rounded px-2 py-1 text-sm min-w-56"
            value={objektId}
            onChange={e => waehleObjekt(e.target.value)}
          >
            <option value="">Objekt wählen…</option>
            {objekte.map(o => (
              <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
            ))}
          </select>
          <select
            className="border rounded px-2 py-1 text-sm min-w-56 disabled:bg-gray-50 disabled:text-gray-400"
            value={einheitId}
            onChange={e => waehleEinheit(e.target.value)}
            disabled={!objektId}
          >
            <option value="">Einheit wählen…</option>
            {einheiten.map(ei => (
              <option key={ei.id} value={ei.id}>
                {ei.einheit_nr}{ei.lage ? ` – ${ei.lage}` : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      {!einheitId && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            {objektId ? 'Bitte oben rechts eine Einheit wählen.'
              : 'Bitte oben rechts Objekt und Einheit wählen.'}
          </p>
        </div>
      )}

      {einheitId && isLoading && (
        <p className="text-sm text-gray-500">Akte wird geladen…</p>
      )}
      {einheitId && isError && (
        <p className="text-sm text-red-700">Die Akte konnte nicht geladen werden.</p>
      )}

      {akte && (
        <Aktenansicht
          akte={akte}
          aktenart="wohnung"
          objektId={objektId}
          kontextKey={einheitId}
          onReload={neuLaden}
        />
      )}
    </div>
  )
}
