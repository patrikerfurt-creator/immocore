import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import type { Verteilerschluessel, Einheit } from '../../types'

const vsTypLabel: Record<string, string> = {
  flaeche: 'Fläche',
  mea: 'MEA',
  kopf: 'Kopf',
  direkt: 'Direkt',
  verbrauch: 'Verbrauch',
}

// ── Detail-Ansicht ────────────────────────────────────────────────────

type WertRow = {
  einheit: Einheit
  wertId: string | null
  beteiligt: boolean
  wert: string
}

function VsDetail({
  vs,
  objektId,
  onBack,
}: {
  vs: Verteilerschluessel
  objektId: string
  onBack: () => void
}) {
  const qc = useQueryClient()
  const [rows, setRows] = useState<WertRow[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: einheiten = [], isLoading } = useQuery({
    queryKey: ['einheiten', objektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: objektId }),
  })

  useEffect(() => {
    if (einheiten.length === 0) return
    const werteMap = Object.fromEntries(vs.werte.map(w => [w.einheit, w]))
    setRows(
      einheiten.map(e => {
        const w = werteMap[e.id]
        return { einheit: e, wertId: w?.id ?? null, beteiligt: !!w, wert: w?.wert ?? '' }
      })
    )
  }, [einheiten, vs.werte])

  function toggleBeteiligt(idx: number) {
    setRows(prev => prev.map((r, i) => (i === idx ? { ...r, beteiligt: !r.beteiligt } : r)))
  }

  function setWert(idx: number, wert: string) {
    setRows(prev => prev.map((r, i) => (i === idx ? { ...r, wert } : r)))
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      for (const row of rows) {
        if (row.beteiligt) {
          await objekteApi.wertSetzen(vs.id, row.einheit.id, row.wert || '0')
        } else if (!row.beteiligt && row.wertId) {
          await objekteApi.deleteWert(row.wertId)
        }
      }
      await qc.invalidateQueries({ queryKey: ['verteilerschluessel', objektId] })
      onBack()
    } catch {
      setError('Fehler beim Speichern. Bitte erneut versuchen.')
      setSaving(false)
    }
  }

  const beteiligtCount = rows.filter(r => r.beteiligt).length
  const summe = rows
    .filter(r => r.beteiligt && r.wert)
    .reduce((acc, r) => acc + parseFloat(r.wert || '0'), 0)

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="text-primary-600 hover:underline text-sm"
        >
          ← Verteilerschlüssel
        </button>
        <span className="text-gray-300">|</span>
        <h1 className="text-2xl font-bold text-gray-900">{vs.bezeichnung}</h1>
        <span className="font-mono text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">{vs.schluessel}</span>
        {vs.vs_typ && (
          <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded font-medium">
            {vsTypLabel[vs.vs_typ] ?? vs.vs_typ}
          </span>
        )}
      </div>

      {/* Info-Zeile */}
      <div className="flex items-center gap-6 mb-4 text-sm text-gray-600">
        <span>{beteiligtCount} Einheiten beteiligt</span>
        {vs.einheit && <span>Einheit: <span className="font-medium">{vs.einheit}</span></span>}
        {summe > 0 && (
          <span>
            Summe:{' '}
            <span className="font-mono font-medium text-gray-900">
              {summe.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </span>
          </span>
        )}
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-center px-4 py-3 font-medium text-gray-600 w-12">
                  Beteiligt
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Fl.-Nr.</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Einheit</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Lage</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Typ</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600 w-40">
                  Wert {vs.einheit ? `(${vs.einheit})` : ''}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr
                  key={row.einheit.id}
                  className={`border-b border-gray-50 transition-colors ${
                    row.beteiligt ? 'hover:bg-gray-50' : 'opacity-40 hover:opacity-60'
                  }`}
                >
                  <td className="px-4 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={row.beteiligt}
                      onChange={() => toggleBeteiligt(idx)}
                      className="w-4 h-4 accent-primary-600 cursor-pointer"
                    />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-600">
                    {row.einheit.flaechennummer || '–'}
                  </td>
                  <td className="px-4 py-2 font-medium text-gray-800">{row.einheit.einheit_nr}</td>
                  <td className="px-4 py-2 text-gray-600">{row.einheit.lage || '–'}</td>
                  <td className="px-4 py-2 text-gray-600">{row.einheit.einheit_typ}</td>
                  <td className="px-4 py-2 text-right">
                    <input
                      type="number"
                      step="0.0001"
                      min="0"
                      value={row.wert}
                      disabled={!row.beteiligt}
                      onChange={e => setWert(idx, e.target.value)}
                      className="w-36 border border-gray-300 rounded px-2 py-1 text-right text-sm font-mono
                                 focus:outline-none focus:ring-1 focus:ring-primary-500
                                 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed"
                      placeholder="0,0000"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="flex justify-end gap-3 mt-4">
        <button
          onClick={onBack}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
        >
          Abbrechen
        </button>
        <button
          onClick={handleSave}
          disabled={saving || isLoading}
          className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
        >
          {saving ? 'Speichern…' : 'Speichern'}
        </button>
      </div>
    </div>
  )
}

// ── Listen-Ansicht ────────────────────────────────────────────────────

export function VerteilerschluesselPage() {
  const [searchParams] = useSearchParams()
  const objektId = searchParams.get('objekt')
  const [selectedVs, setSelectedVs] = useState<Verteilerschluessel | null>(null)

  const { data: vsList = [], isLoading } = useQuery({
    queryKey: ['verteilerschluessel', objektId],
    queryFn: () => objekteApi.verteilerschluessel({ objekt: objektId! }),
    enabled: !!objektId,
  })

  // Wenn nach dem Speichern die Liste neu geladen wird, selectedVs aktualisieren
  useEffect(() => {
    if (selectedVs && vsList.length > 0) {
      const updated = vsList.find(v => v.id === selectedVs.id)
      if (updated) setSelectedVs(updated)
    }
  }, [vsList])

  if (!objektId) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Verteilerschlüssel</h1>
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500 mb-3">Bitte wählen Sie zuerst ein Objekt aus.</p>
          <Link to="/objekte" className="text-primary-600 hover:underline text-sm">
            → Zur Objektliste
          </Link>
        </div>
      </div>
    )
  }

  if (selectedVs) {
    return (
      <VsDetail
        vs={selectedVs}
        objektId={objektId}
        onBack={() => setSelectedVs(null)}
      />
    )
  }

  if (isLoading) return <p className="text-gray-400">Laden…</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Verteilerschlüssel</h1>
        <span className="text-sm text-gray-500">{vsList.length} Schlüssel</span>
      </div>

      {vsList.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500">Keine Verteilerschlüssel für dieses Objekt vorhanden.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Schlüssel</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Typ</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Einheit</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Summe</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Werte</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Aktiv</th>
              </tr>
            </thead>
            <tbody>
              {vsList.map(vs => (
                <tr
                  key={vs.id}
                  onClick={() => setSelectedVs(vs)}
                  className={`border-b border-gray-50 hover:bg-primary-50 cursor-pointer transition-colors ${
                    !vs.aktiv ? 'opacity-50' : ''
                  }`}
                >
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-gray-700">{vs.schluessel}</td>
                  <td className="px-4 py-2.5 text-gray-800 font-medium">{vs.bezeichnung}</td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {vs.vs_typ ? vsTypLabel[vs.vs_typ] ?? vs.vs_typ : '–'}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs">{vs.einheit || '–'}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-700">
                    {vs.summe
                      ? parseFloat(vs.summe).toLocaleString('de-DE', { minimumFractionDigits: 2 })
                      : '–'}
                  </td>
                  <td className="px-4 py-2.5 text-center text-gray-500">{vs.werte.length}</td>
                  <td className="px-4 py-2.5 text-center">
                    {vs.aktiv
                      ? <span className="text-green-600 text-xs font-medium">Aktiv</span>
                      : <span className="text-gray-400 text-xs">Inaktiv</span>}
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
