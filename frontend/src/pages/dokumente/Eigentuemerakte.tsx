import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { aktenApi } from '../../api/akten'
import { personenApi } from '../../api/personen'
import Aktenansicht from '../../components/akten/Aktenansicht'

/**
 * Eigentümerakte einer Person — zeitlich auf ihre Besitzzeit begrenzt (die
 * Logik dazu steckt im Backend). Darstellung wie Haus-/Wohnungsakte, aber ohne
 * Objektbezug: deshalb kein Registervorschlag-Objekt und keine
 * Untergliederung (das regelt <Aktenansicht> über das fehlende objektId).
 *
 * "nur aktuelle" blendet beendete Eigentumsverhältnisse aus — die Frage "was
 * gehört der Person heute" statt "was sie je betraf".
 */
export default function Eigentuemerakte() {
  const qc = useQueryClient()
  const [suchParams, setSuchParams] = useSearchParams()
  const personId = suchParams.get('person') ?? ''
  const nurAktuelle = suchParams.get('nur_aktuelle') === '1'

  const { data: personen = [] } = useQuery({
    queryKey: ['personen', 'eigentuemer'],
    queryFn: () => personenApi.list({ person_typ: '100' }),
  })

  const { data: akte, isLoading, isError } = useQuery({
    queryKey: ['eigentuemerakte', personId, nurAktuelle],
    queryFn: () => aktenApi.eigentuemerakte(personId, nurAktuelle),
    enabled: Boolean(personId),
  })

  const neuLaden = () =>
    qc.invalidateQueries({ queryKey: ['eigentuemerakte', personId, nurAktuelle] })

  const setzeParams = (person: string, aktuell: boolean) =>
    setSuchParams(person
      ? { person, ...(aktuell ? { nur_aktuelle: '1' } : {}) }
      : {})

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Eigentümerakte</h1>
          {akte && (
            <span className="text-sm text-gray-500">
              {akte.anzahl_dokumente} Dokument{akte.anzahl_dokumente === 1 ? '' : 'e'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={nurAktuelle}
              onChange={e => setzeParams(personId, e.target.checked)}
              disabled={!personId}
            />
            nur aktuelle
          </label>
          <select
            className="border rounded px-2 py-1 text-sm min-w-72"
            value={personId}
            onChange={e => setzeParams(e.target.value, nurAktuelle)}
          >
            <option value="">Eigentümer wählen…</option>
            {personen.map(p => (
              <option key={p.id} value={p.id}>{p.personennummer} – {p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {!personId && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            Bitte oben rechts einen Eigentümer wählen.
          </p>
        </div>
      )}

      {personId && isLoading && (
        <p className="text-sm text-gray-500">Akte wird geladen…</p>
      )}
      {personId && isError && (
        <p className="text-sm text-red-700">Die Akte konnte nicht geladen werden.</p>
      )}

      {akte && (
        <Aktenansicht
          akte={akte}
          aktenart="eigentuemer"
          kontextKey={`${personId}:${nurAktuelle}`}
          onReload={neuLaden}
        />
      )}
    </div>
  )
}
