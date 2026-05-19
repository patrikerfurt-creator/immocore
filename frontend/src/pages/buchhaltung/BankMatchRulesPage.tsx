import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { buchhaltungApi } from '../../api/buchhaltung'
import { Badge } from '../../components/ui/Badge'
import { useObjektStore } from '../../stores/objekt'
import type { BankMatchRegel } from '../../types'

const DATUM = (s: string | null) => s ? new Date(s).toLocaleDateString('de-DE') : '—'

const ERSTELLT_AUS_LABELS: Record<string, string> = {
  bestaetigung: 'Bestätigung',
  korrektur:    'Korrektur',
  manuell:      'Manuell',
}

export function BankMatchRulesPage() {
  const objektId = useObjektStore(s => s.selectedId)
  const [statusFilter, setStatusFilter] = useState<'alle' | 'aktiv' | 'veraltet'>('aktiv')
  const qc = useQueryClient()

  const { data: regeln, isLoading } = useQuery({
    queryKey: ['bank-match-regeln', objektId, statusFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (statusFilter !== 'alle') params.status = statusFilter
      return buchhaltungApi.eBankingMatchRegeln(params)
    },
    enabled: !!objektId,
  })

  const deaktivierenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.eBankingMatchRegelDeaktivieren(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bank-match-regeln'] }),
  })

  if (!objektId) {
    return (
      <div className="p-6 text-gray-500">Bitte zuerst ein Objekt in der Seitenleiste auswählen.</div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <Link
            to="/buchhaltung/ebanking"
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← E-Banking
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Lernregeln</h1>
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        {(['aktiv', 'veraltet', 'alle'] as const).map(v => (
          <button
            key={v}
            onClick={() => setStatusFilter(v)}
            className={`px-3 py-1.5 text-sm rounded border transition-colors ${
              statusFilter === v
                ? 'bg-blue-600 text-white border-blue-600'
                : 'border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {v === 'alle' ? 'Alle' : v === 'aktiv' ? 'Aktiv' : 'Veraltet'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Lade Regeln…</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Kontrahent-IBAN</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Gegenkonto</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Quelle</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium">Treffer</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Zuletzt</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(regeln ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-10 text-gray-400">
                    Keine Regeln vorhanden
                  </td>
                </tr>
              ) : (regeln ?? []).map((r: BankMatchRegel) => (
                <tr key={r.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{r.kontrahent_iban || '—'}</td>
                  <td className="px-4 py-3">
                    {r.gegenkonto_detail
                      ? `${r.gegenkonto_detail.kontonummer} — ${r.gegenkonto_detail.kontoname}`
                      : <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {ERSTELLT_AUS_LABELS[r.erstellt_aus] ?? r.erstellt_aus}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{r.trefferzahl}</td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                    {DATUM(r.letzte_anwendung)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={r.status} label={r.status === 'aktiv' ? 'Aktiv' : 'Veraltet'} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {r.status === 'aktiv' && (
                      <button
                        onClick={() => deaktivierenMut.mutate(r.id)}
                        disabled={deaktivierenMut.isPending}
                        className="text-xs text-gray-400 hover:text-red-600 border border-gray-200 rounded px-2 py-1 hover:border-red-200 transition-colors"
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
