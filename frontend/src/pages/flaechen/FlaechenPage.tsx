import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'

export function FlaechenPage() {
  const [selectedObjektId, setSelectedObjektId] = useState('')

  const { data: objekte = [] } = useQuery({ queryKey: ['objekte-list'], queryFn: objekteApi.list })

  const { data: einheiten = [], isLoading: loadingE } = useQuery({
    queryKey: ['einheiten', selectedObjektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: selectedObjektId }),
    enabled: !!selectedObjektId,
  })

  const { data: evs = [], isLoading: loadingEV } = useQuery({
    queryKey: ['eigentumsverhaeltnisse', 'objekt', selectedObjektId],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ objekt: selectedObjektId, aktiv: 'true' }),
    enabled: !!selectedObjektId,
  })

  const evByEinheit = useMemo(
    () => new Map(evs.map(ev => [ev.einheit, ev])),
    [evs],
  )

  const isLoading = loadingE || loadingEV

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Flächen</h1>

      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Objekt:</label>
        <select
          value={selectedObjektId}
          onChange={e => setSelectedObjektId(e.target.value)}
          className="rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none min-w-[300px]"
        >
          <option value="">– Objekt wählen –</option>
          {objekte.map(o => (
            <option key={o.id} value={o.id}>
              {o.objektnummer} · {o.bezeichnung}
            </option>
          ))}
        </select>
      </div>

      {selectedObjektId && (
        isLoading ? (
          <p className="text-sm text-gray-400">Laden…</p>
        ) : einheiten.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Einheiten gefunden.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Fl-Nr.</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Bez. Einheit</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Lage</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Eigentümer</th>
                </tr>
              </thead>
              <tbody>
                {einheiten.map(e => {
                  const ev = evByEinheit.get(e.id)
                  return (
                    <tr key={e.id} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-500">{e.flaechennummer || '–'}</td>
                      <td className="px-4 py-3 font-medium text-gray-800">{e.einheit_nr}</td>
                      <td className="px-4 py-3 text-gray-600">{e.lage}</td>
                      <td className="px-4 py-3 text-gray-800">
                        {ev
                          ? ev.person_name
                          : <span className="text-gray-400 italic text-xs">–</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
