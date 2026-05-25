import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useObjektStore } from '../../../stores/objekt'
import { wirtschaftsplanApi } from '../../../api/wirtschaftsplan'

const STATUS_LABEL: Record<string, string> = {
  entwurf: 'Entwurf',
  beschlossen: 'Beschlossen',
  aktiv: 'Aktiv',
  aufgehoben: 'Aufgehoben',
}
const STATUS_COLOR: Record<string, string> = {
  entwurf: 'bg-yellow-100 text-yellow-800',
  beschlossen: 'bg-blue-100 text-blue-800',
  aktiv: 'bg-green-100 text-green-800',
  aufgehoben: 'bg-gray-100 text-gray-500',
}

function fmt(betrag: string | number) {
  return Number(betrag).toLocaleString('de-DE', { minimumFractionDigits: 2 })
}

export function WirtschaftsplanListe() {
  const navigate = useNavigate()
  const { selectedId } = useObjektStore()
  const params: Record<string, string> = {}
  if (selectedId) params.objekt = selectedId

  const { data: plaene = [], isLoading } = useQuery({
    queryKey: ['wirtschaftsplaene', selectedId],
    queryFn: () => wirtschaftsplanApi.list(params),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Wirtschaftspläne</h1>
        {selectedId && (
          <button
            onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/neu?objekt=${selectedId}`)}
            className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
          >
            + Neuer Wirtschaftsplan
          </button>
        )}
      </div>

      {!selectedId && (
        <p className="text-sm text-gray-500">Bitte oben ein Objekt auswählen.</p>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400">Lade...</p>
      ) : plaene.length === 0 && selectedId ? (
        <p className="text-sm text-gray-400">Noch keine Wirtschaftspläne vorhanden.</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Wirtschaftsjahr</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Wirkung ab</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">Gesamtsumme</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600">davon Hausgeld</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Beschluss</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {plaene.map(wp => (
                <tr
                  key={wp.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wp.id}`)}
                >
                  <td className="px-4 py-3 font-medium">{wp.wirtschaftsjahr_jahr}</td>
                  <td className="px-4 py-3">{wp.wirkung_ab}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[wp.status]}`}>
                      {STATUS_LABEL[wp.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">{fmt(wp.gesamtsumme)} €</td>
                  <td className="px-4 py-3 text-right font-mono">{fmt(wp.gesamtsumme_hausgeld)} €</td>
                  <td className="px-4 py-3 text-gray-500">
                    {wp.beschluss_datum ?? '—'}
                    {wp.beschluss_tagesordnungspunkt && (
                      <span className="text-xs text-gray-400 ml-1">({wp.beschluss_tagesordnungspunkt})</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
