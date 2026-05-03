import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import type { RechnungsMatchRegel } from '../../types'

const DATUM = (s: string | null) => s ? new Date(s).toLocaleDateString('de-DE') : '—'

const ERSTELLT_AUS_LABEL: Record<string, string> = {
  pruefung:           'Prüffall',
  freigabe_korrektur: 'Freigabe-Korrektur',
  manuell:            'Manuell',
}

export default function MatchRegeln() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('aktiv')
  const [search, setSearch] = useState('')

  const { data: regeln = [], isLoading } = useQuery<RechnungsMatchRegel[]>({
    queryKey: ['match-regeln', statusFilter],
    queryFn: () => rechnungenApi.matchRegeln(statusFilter !== 'alle' ? { status: statusFilter } : {}),
  })

  const mutDeaktivieren = useMutation({
    mutationFn: (id: string) => rechnungenApi.matchRegelDeaktivieren(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['match-regeln'] }),
  })

  const gefiltert = regeln.filter(r =>
    !search ||
    r.kreditor_name.toLowerCase().includes(search.toLowerCase()) ||
    r.objekt_bezeichnung.toLowerCase().includes(search.toLowerCase()) ||
    r.leistungstext_sample.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-semibold">Match-Regeln</h1>
        <div className="flex gap-3">
          <input
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Suche Kreditor, Objekt, Leistungstext …"
            className="border rounded px-3 py-1.5 text-sm w-64"
          />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm"
          >
            <option value="aktiv">Nur aktive</option>
            <option value="veraltet">Nur veraltete</option>
            <option value="alle">Alle</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <p className="text-gray-500 text-sm">Lade…</p>
      ) : gefiltert.length === 0 ? (
        <p className="text-gray-500 text-sm">Keine Match-Regeln gefunden.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-3 py-2">Kreditor</th>
                <th className="px-3 py-2">Objekt</th>
                <th className="px-3 py-2">Leistungstext (Sample)</th>
                <th className="px-3 py-2">Konto</th>
                <th className="px-3 py-2">Quelle</th>
                <th className="px-3 py-2 text-center">Treffer</th>
                <th className="px-3 py-2">Letzte Anw.</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {gefiltert.map(r => (
                <tr key={r.id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium">{r.kreditor_name}</td>
                  <td className="px-3 py-2 text-gray-600">{r.objekt_bezeichnung}</td>
                  <td className="px-3 py-2 text-gray-500 max-w-xs truncate" title={r.leistungstext_sample}>
                    {r.leistungstext_sample || <span className="italic text-gray-400">—</span>}
                  </td>
                  <td className="px-3 py-2">{r.konto_label}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      r.erstellt_aus === 'pruefung'           ? 'bg-yellow-100 text-yellow-700' :
                      r.erstellt_aus === 'freigabe_korrektur' ? 'bg-blue-100 text-blue-700'     :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {ERSTELLT_AUS_LABEL[r.erstellt_aus] ?? r.erstellt_aus}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center font-mono">{r.trefferzahl}</td>
                  <td className="px-3 py-2 text-gray-500">{DATUM(r.letzte_anwendung)}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      r.status === 'aktiv' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {r.status === 'aktiv' && (
                      <button
                        onClick={() => mutDeaktivieren.mutate(r.id)}
                        disabled={mutDeaktivieren.isPending}
                        className="text-xs text-red-600 hover:underline"
                      >
                        Deaktivieren
                      </button>
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
