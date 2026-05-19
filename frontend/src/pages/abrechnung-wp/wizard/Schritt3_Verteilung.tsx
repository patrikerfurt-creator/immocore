import { Fragment, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi, type Wirtschaftsplan, type WirtschaftsplanPosition } from '../../../api/wirtschaftsplan'

interface Props {
  wp: Wirtschaftsplan
  onWeiter: () => void
  onZurueck: () => void
}

function diffBadge(pos: WirtschaftsplanPosition) {
  const diff = Math.abs(parseFloat(pos.differenz))
  if (diff <= 0.10) return { icon: '🟢', text: 'ok', color: 'text-green-700' }
  if (diff <= 1.00) return { icon: '🟡', text: `Δ ${diff.toFixed(2)} €`, color: 'text-amber-700' }
  return { icon: '🔴', text: `Δ ${diff.toFixed(2)} €`, color: 'text-red-600' }
}

function fmtEur(val: string) {
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
}

export function Schritt3_Verteilung({ wp, onWeiter, onZurueck }: Props) {
  const qc = useQueryClient()
  const [expandedPos, setExpandedPos] = useState<string | null>(null)
  const [freigabeLoading, setFreigabeLoading] = useState<Record<string, boolean>>({})

  const freigabeMut = useMutation({
    mutationFn: (posId: string) => wirtschaftsplanApi.freigabeTrotzDiff(wp.id, posId),
    onMutate: (posId) => setFreigabeLoading(f => ({ ...f, [posId]: true })),
    onSettled: (_, __, posId) => {
      setFreigabeLoading(f => ({ ...f, [posId]: false }))
      qc.invalidateQueries({ queryKey: ['wirtschaftsplan', wp.id] })
    },
  })

  const positionen = wp.positionen ?? []
  const alleValidiert = positionen.every(p => p.verteilung_validiert || p.verteilung_freigegeben_trotz_diff)
  const offenCount = positionen.filter(p => !p.verteilung_validiert && !p.verteilung_freigegeben_trotz_diff).length

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-800 mb-1">Verteilungsvalidierung</h2>
      <p className="text-sm text-gray-500 mb-4">
        Prüfe ob die Summe der Einheitenanteile mit dem Positionsbetrag übereinstimmt (Toleranz ±0,10 €).
      </p>

      {offenCount > 0 && (
        <div className="mb-4 rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-700">
          {offenCount} Position{offenCount > 1 ? 'en' : ''} noch nicht validiert oder freigegeben.
        </div>
      )}

      <div className="rounded-lg border border-gray-200 overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-20">Konto</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Bezeichnung</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-14">VS</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-28">Betrag</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-28">Anteile-Σ</th>
              <th className="text-center px-4 py-2.5 font-medium text-gray-600 w-28">Status</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {positionen.map(pos => {
              const badge = diffBadge(pos)
              const isExpanded = expandedPos === pos.id
              const isOk = pos.verteilung_validiert
              const isFreigegeben = pos.verteilung_freigegeben_trotz_diff
              const diff = Math.abs(parseFloat(pos.differenz))
              const showFreigabe = !isOk && !isFreigegeben && diff > 0.10

              return (
                <Fragment key={pos.id}>
                  <tr
                    className={`border-t border-gray-100 cursor-pointer hover:bg-gray-50 ${isExpanded ? 'bg-gray-50' : ''}`}
                    onClick={() => setExpandedPos(isExpanded ? null : pos.id)}
                  >
                    <td className="px-4 py-2.5 font-mono text-gray-500 text-xs">{pos.kontonummer}</td>
                    <td className="px-4 py-2.5 text-gray-700">{pos.kontoname}</td>
                    <td className="px-4 py-2.5 text-gray-400 font-mono text-xs">{pos.vs_code}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{fmtEur(pos.betrag)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-600">{fmtEur(pos.anteile_summe)}</td>
                    <td className="px-4 py-2.5 text-center">
                      {isOk ? (
                        <span className="text-xs text-green-700 font-medium">🟢 ok</span>
                      ) : isFreigegeben ? (
                        <span className="text-xs text-blue-600 font-medium">✓ freigegeben</span>
                      ) : (
                        <span className={`text-xs font-medium ${badge.color}`}>{badge.icon} {badge.text}</span>
                      )}
                    </td>
                    <td className="px-2 py-2.5 text-gray-400 text-xs">{isExpanded ? '▲' : '▼'}</td>
                  </tr>
                  {isExpanded && (
                    <tr className="bg-gray-50">
                      <td colSpan={7} className="px-4 py-3 border-t border-gray-100">
                        {pos.anteile.length === 0 ? (
                          <p className="text-xs text-gray-400">Keine Anteile berechnet.</p>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-gray-500">
                                  <th className="text-left py-1 pr-4 font-medium">Einheit</th>
                                  <th className="text-left py-1 pr-4 font-medium">Lage</th>
                                  <th className="text-right py-1 pr-4 font-medium">VS-Anteil</th>
                                  <th className="text-right py-1 font-medium">Jahresbetrag</th>
                                </tr>
                              </thead>
                              <tbody>
                                {pos.anteile.map(a => (
                                  <tr key={a.id} className="border-t border-gray-200">
                                    <td className="py-1 pr-4 font-mono">{a.einheit_nr}</td>
                                    <td className="py-1 pr-4 text-gray-600">{a.einheit_lage}</td>
                                    <td className="py-1 pr-4 text-right text-gray-600">
                                      {(parseFloat(a.vs_anteil_einheit) / parseFloat(a.vs_anteil_gesamt) * 100).toFixed(4)} %
                                    </td>
                                    <td className="py-1 text-right text-gray-700">
                                      {parseFloat(a.betrag_anteil).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        {showFreigabe && (
                          <div className="mt-3 flex items-center gap-3">
                            <p className="text-xs text-amber-700">
                              Differenz {parseFloat(pos.differenz).toFixed(2)} € — trotzdem freigeben?
                            </p>
                            <button
                              onClick={(e) => { e.stopPropagation(); freigabeMut.mutate(pos.id) }}
                              disabled={freigabeLoading[pos.id]}
                              className="text-xs bg-amber-100 text-amber-800 border border-amber-300 px-3 py-1 rounded hover:bg-amber-200 disabled:opacity-50"
                            >
                              {freigabeLoading[pos.id] ? '…' : 'Trotzdem freigeben'}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between">
        <button onClick={onZurueck} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
          ← Zurück
        </button>
        <button
          onClick={onWeiter}
          disabled={!alleValidiert}
          className="bg-primary-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-primary-700 disabled:opacity-40"
          title={!alleValidiert ? 'Alle Positionen müssen validiert oder freigegeben sein' : ''}
        >
          Weiter →
        </button>
      </div>
    </div>
  )
}
