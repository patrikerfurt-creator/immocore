import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useObjektStore } from '../../../stores/objekt'
import { jahresabrechnungApi } from '../../../api/jahresabrechnung'

const STATUS_LABEL: Record<string, string> = {
  entwurf: 'Entwurf',
  freigegeben: 'Freigegeben',
  gesperrt: 'Gesperrt',
}
const STATUS_COLOR: Record<string, string> = {
  entwurf: 'bg-yellow-100 text-yellow-800',
  freigegeben: 'bg-blue-100 text-blue-800',
  gesperrt: 'bg-green-100 text-green-800',
}

export function JahresabrechnungListe() {
  const navigate = useNavigate()
  const { selectedId, selectedTyp } = useObjektStore()

  const { data: abrechnungen = [], isLoading } = useQuery({
    queryKey: ['jahresabrechnungen', selectedId],
    queryFn: () => jahresabrechnungApi.list(selectedId ? { objekt: selectedId } : undefined),
    enabled: !!selectedId,
  })

  const istWeg = selectedTyp === 'WEG'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Jahresabrechnungen</h1>
        {selectedId && istWeg && (
          <button
            onClick={() => navigate(`/abrechnung-wp/jahresabrechnung/wizard?objekt=${selectedId}`)}
            className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
          >
            + Neue Jahresabrechnung
          </button>
        )}
      </div>

      {!selectedId && (
        <p className="text-sm text-gray-500">Bitte oben ein Objekt auswählen.</p>
      )}
      {selectedId && !istWeg && (
        <div className="rounded-md bg-amber-50 border border-amber-300 p-3 text-sm text-amber-700">
          Die Jahresabrechnung ist nur für WEG-Objekte verfügbar.
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400">Lade...</p>
      ) : abrechnungen.length === 0 && selectedId && istWeg ? (
        <p className="text-sm text-gray-400">Noch keine Jahresabrechnungen vorhanden.</p>
      ) : abrechnungen.length > 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Wirtschaftsjahr</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Erstellt am</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Schritt</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Freigegeben</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {abrechnungen.map(ja => (
                <tr
                  key={ja.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() =>
                    navigate(`/abrechnung-wp/jahresabrechnung/wizard?objekt=${ja.objekt}&ja=${ja.id}`)
                  }
                >
                  <td className="px-4 py-3 font-medium">{ja.wirtschaftsjahr_jahr}</td>
                  <td className="px-4 py-3">{ja.erstellungsdatum}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[ja.status]}`}>
                      {STATUS_LABEL[ja.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {ja.status === 'entwurf' ? `${ja.current_step} / 8` : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {ja.freigegeben_am
                      ? `${new Date(ja.freigegeben_am).toLocaleDateString('de-DE')} (${ja.freigegeben_von_name ?? '—'})`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
