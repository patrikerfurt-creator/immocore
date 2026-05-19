import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useObjektStore } from '../../stores/objekt'
import { rechnungenApi } from '../../api/rechnungen'
import { zahlungsverkehrApi } from '../../api/zahlungsverkehr'

import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { RechnungList } from '../../types'

function formatEuro(val: string | number | null | undefined) {
  if (val == null) return '—'
  return Number(val).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

function formatDatum(s: string | null | undefined) {
  if (!s) return '—'
  const [y, m, d] = s.split('-')
  return `${d}.${m}.${y}`
}

export function Zahlungen() {
  const objektId = useObjektStore(s => s.selectedId)
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [faelligkeitsdatum, setFaelligkeitsdatum] = useState(
    new Date().toISOString().split('T')[0]
  )
  const [error, setError] = useState<string | null>(null)

  // Alle gebucht-Rechnungen laden — objektübergreifend wenn kein Objekt gewählt
  const { data: rechnungen, isLoading } = useQuery({
    queryKey: ['rechnungen-zahlung', objektId],
    queryFn: () =>
      rechnungenApi.list(
        objektId
          ? { objekt: objektId, status: 'gebucht' }
          : { status: 'gebucht' }
      ),
    enabled: true,
  })

  const exportMut = useMutation({
    mutationFn: zahlungsverkehrApi.exportRechnungenSepa,
    onSuccess: () => {
      setError(null)
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['rechnungen-zahlung'] })
      qc.invalidateQueries({ queryKey: ['rechnungen'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'Fehler beim Export')
    },
  })

  function handleExport() {
    if (selected.size === 0) return
    setError(null)
    exportMut.mutate({
      rechnung_ids: Array.from(selected),
      faelligkeitsdatum,
    })
  }

  function toggleAll() {
    const zahlbare = (rechnungen ?? []).filter(kannBezahlen)
    if (selected.size === zahlbare.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(zahlbare.map((r: RechnungList) => r.id)))
    }
  }

  function kannBezahlen(r: RechnungList) {
    return r.status === 'gebucht' && !!r.aufwandskonto_id && !!r.betrag_brutto && !!r.kreditor_name
  }

  const zahlbareRechnungen = (rechnungen ?? []).filter(kannBezahlen)
  const summeSelected = (rechnungen ?? [])
    .filter((r: RechnungList) => selected.has(r.id))
    .reduce((s: number, r: RechnungList) => s + Number(r.betrag_brutto ?? 0), 0)

  // Anzahl unterschiedliche Objekte in Auswahl
  const selectedRechnungen = (rechnungen ?? []).filter(r => selected.has(r.id))
  const objekteInAuswahl = new Set(selectedRechnungen.map(r => r.objekt_id)).size

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Zahlungslauf</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Freigegebene Rechnungen (Status: gebucht) — bereit zur Zahlung
            {!objektId && <span className="ml-1 text-blue-600">· alle Objekte</span>}
          </p>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-5 flex items-center gap-4 flex-wrap">
          <div>
            <span className="font-medium text-blue-800">
              {selected.size} {selected.size === 1 ? 'Rechnung' : 'Rechnungen'} ausgewählt
              {' — '}
              {formatEuro(summeSelected)}
            </span>
            {objekteInAuswahl > 1 && (
              <span className="ml-2 text-xs text-blue-600">
                ({objekteInAuswahl} Objekte — je Objekt wird das Zahlungsverkehrskonto verwendet)
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 ml-auto">
            <input
              type="date"
              className="border rounded px-3 py-1.5 text-sm"
              value={faelligkeitsdatum}
              onChange={e => setFaelligkeitsdatum(e.target.value)}
            />
            <Button onClick={handleExport} disabled={exportMut.isPending}>
              {exportMut.isPending ? 'Wird exportiert…' : 'SEPA XML herunterladen'}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {isLoading && <p className="text-gray-500 text-sm">Wird geladen…</p>}

      {!isLoading && zahlbareRechnungen.length === 0 && (
        <p className="text-gray-500 text-sm">
          Keine freigegebenen Rechnungen (Status &ldquo;gebucht&rdquo;) vorhanden.
        </p>
      )}

      {zahlbareRechnungen.length > 0 && (
        <div className="bg-white border rounded-lg overflow-hidden shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={selected.size === zahlbareRechnungen.length && zahlbareRechnungen.length > 0}
                    onChange={toggleAll}
                    className="rounded"
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Kreditor</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Objekt</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Rechnungsnr.</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Datum</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Sachkonto</th>
                <th className="px-4 py-3 text-right font-medium text-gray-700">Betrag</th>
                <th className="px-4 py-3 text-left font-medium text-gray-700">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {zahlbareRechnungen.map((r: RechnungList) => (
                <tr
                  key={r.id}
                  className={`hover:bg-gray-50 cursor-pointer ${selected.has(r.id) ? 'bg-blue-50' : ''}`}
                  onClick={() => {
                    setSelected(prev => {
                      const next = new Set(prev)
                      if (next.has(r.id)) next.delete(r.id)
                      else next.add(r.id)
                      return next
                    })
                  }}
                >
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => {
                        setSelected(prev => {
                          const next = new Set(prev)
                          if (next.has(r.id)) next.delete(r.id)
                          else next.add(r.id)
                          return next
                        })
                      }}
                      className="rounded"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium">{r.kreditor_name || '—'}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">{r.objekt_bezeichnung || '—'}</td>
                  <td className="px-4 py-3 text-gray-600">{r.rechnungsnummer || '—'}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDatum(r.rechnungsdatum)}</td>
                  <td className="px-4 py-3 text-xs text-gray-600">{r.aufwandskonto_label || '—'}</td>
                  <td className="px-4 py-3 text-right font-mono">{formatEuro(r.betrag_brutto)}</td>
                  <td className="px-4 py-3">
                    <Badge value={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 border-t">
              <tr>
                <td colSpan={6} className="px-4 py-2 text-sm font-medium text-gray-600">
                  Gesamt ({zahlbareRechnungen.length} Rechnungen)
                </td>
                <td className="px-4 py-2 text-right font-mono font-medium">
                  {formatEuro(
                    zahlbareRechnungen.reduce(
                      (s: number, r: RechnungList) => s + Number(r.betrag_brutto ?? 0),
                      0
                    )
                  )}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}
