import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AktenDokument, aktenApi, ObjektGruppe } from '../../api/akten'
import { dokumenteApi } from '../../api/dokumente'
import { rechnungenApi } from '../../api/rechnungen'

/**
 * Kreditorenakte — alle Belege eines Kreditors quer über die Objekte, nach
 * Liegenschaft gruppiert. Bewusst read-only: diese Belege sind
 * Rechnungsbelege, die in der jeweiligen Hausakte einsortiert werden; die
 * Kreditorenakte ist nur eine zweite Sicht darauf. Deshalb kein Registerbaum
 * und kein Einsortieren (anders als Haus-/Wohnungs-/Eigentümerakte).
 */

function datum(wert: string | null): string {
  if (!wert) return '—'
  return new Date(wert).toLocaleDateString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

function BelegZeile({ dokument }: { dokument: AktenDokument }) {
  return (
    <li className="flex items-baseline justify-between gap-3 py-1.5 border-b border-gray-100 last:border-0">
      <button
        type="button"
        onClick={() => (dokument.ist_mail
          ? dokumenteApi.openMailVorschau(dokument.id)
          : dokumenteApi.openDatei(dokument.id))}
        className="text-sm text-blue-700 hover:underline text-left break-words"
        title={`${dokument.dateiname}
${dokument.ist_mail ? 'Als Textvorschau öffnen' : 'Öffnen'}`}
      >
        {dokument.ist_mail ? '✉ ' : '📄 '}{dokument.anzeigename}
      </button>
      <span className="text-xs text-gray-400 whitespace-nowrap">
        {datum(dokument.dokument_datum ?? dokument.hochgeladen_am)}
      </span>
    </li>
  )
}

function ObjektGruppeKarte({ gruppe }: { gruppe: ObjektGruppe }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium text-gray-900">
          {gruppe.objektnummer && <span className="text-gray-400 mr-1.5">{gruppe.objektnummer}</span>}
          {gruppe.bezeichnung}
        </h2>
        <span className="text-xs text-gray-500 tabular-nums">
          {gruppe.anzahl} Beleg{gruppe.anzahl === 1 ? '' : 'e'}
        </span>
      </div>
      <ul className="px-4 py-1">
        {gruppe.dokumente.map(d => <BelegZeile key={d.id} dokument={d} />)}
      </ul>
    </div>
  )
}

export default function Kreditorenakte() {
  const [suchParams, setSuchParams] = useSearchParams()
  const kreditorId = suchParams.get('kreditor') ?? ''

  const { data: kreditoren = [] } = useQuery({
    queryKey: ['kreditoren'],
    queryFn: () => rechnungenApi.kreditoren(),
  })

  const { data: akte, isLoading, isError } = useQuery({
    queryKey: ['kreditorenakte', kreditorId],
    queryFn: () => aktenApi.kreditorenakte(kreditorId),
    enabled: Boolean(kreditorId),
  })

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] min-h-[32rem]">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-gray-900">Kreditorenakte</h1>
          {akte && (
            <span className="text-sm text-gray-500">
              {akte.anzahl_dokumente} Beleg{akte.anzahl_dokumente === 1 ? '' : 'e'}
            </span>
          )}
        </div>
        <select
          className="border rounded px-2 py-1 text-sm min-w-72"
          value={kreditorId}
          onChange={e => setSuchParams(e.target.value ? { kreditor: e.target.value } : {})}
        >
          <option value="">Kreditor wählen…</option>
          {kreditoren.map(k => (
            <option key={k.id} value={k.id}>{k.kreditorennummer} – {k.name}</option>
          ))}
        </select>
      </div>

      {!kreditorId && (
        <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
          <p className="text-sm text-gray-500">
            Bitte oben rechts einen Kreditor wählen.
          </p>
        </div>
      )}

      {kreditorId && isLoading && (
        <p className="text-sm text-gray-500">Akte wird geladen…</p>
      )}
      {kreditorId && isError && (
        <p className="text-sm text-red-700">Die Akte konnte nicht geladen werden.</p>
      )}

      {akte && (
        akte.objekte.length === 0 ? (
          <div className="flex-1 flex items-center justify-center border border-gray-200 rounded-lg bg-white">
            <p className="text-sm text-gray-400">Für diesen Kreditor gibt es keine Belege.</p>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto flex flex-col gap-3">
            {akte.objekte.map(g => (
              <ObjektGruppeKarte key={g.objekt_id ?? 'ohne'} gruppe={g} />
            ))}
          </div>
        )
      )}
    </div>
  )
}
