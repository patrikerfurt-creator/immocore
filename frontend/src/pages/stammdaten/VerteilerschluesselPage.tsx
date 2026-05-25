import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
  wirtschaftsjahr,
  onBack,
}: {
  vs: Verteilerschluessel
  objektId: string
  wirtschaftsjahr: number
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
          await objekteApi.wertSetzen(vs.id, row.einheit.id, row.wert || '0', wirtschaftsjahr)
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
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="text-primary-600 hover:underline text-sm">
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
        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">
          {wirtschaftsjahr === 0 ? 'Zeitlos' : `WJ ${wirtschaftsjahr}`}
        </span>
      </div>

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
                <th className="text-center px-4 py-3 font-medium text-gray-600 w-12">Beteiligt</th>
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
        <button onClick={onBack} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
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
  const qc = useQueryClient()

  const [selectedVs, setSelectedVs] = useState<Verteilerschluessel | null>(null)
  const [selectedWj, setSelectedWj] = useState<number>(0)
  const [kopierenOffen, setKopierenOffen] = useState(false)
  const [zielWj, setZielWj] = useState('')
  const [kopierenResult, setKopierenResult] = useState<string | null>(null)

  const { data: wirtschaftsjahre = [] } = useQuery({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => objekteApi.wirtschaftsjahre(objektId!),
    enabled: !!objektId,
  })

  const { data: vsList = [], isLoading } = useQuery({
    queryKey: ['verteilerschluessel', objektId, selectedWj],
    queryFn: () => objekteApi.verteilerschluessel({
      objekt: objektId!,
      wirtschaftsjahr: String(selectedWj),
    }),
    enabled: !!objektId,
  })

  useEffect(() => {
    if (selectedVs && vsList.length > 0) {
      const updated = vsList.find(v => v.id === selectedVs.id)
      if (updated) setSelectedVs(updated)
    }
  }, [vsList])

  // Vorschlag für Ziel-WJ: max vorhandenes WJ + 1 oder selectedWj + 1
  useEffect(() => {
    if (wirtschaftsjahre.length > 0) {
      const maxJahr = Math.max(...wirtschaftsjahre.map(w => w.jahr))
      setZielWj(String(selectedWj === 0 ? maxJahr + 1 : selectedWj + 1))
    }
  }, [wirtschaftsjahre, selectedWj])

  const kopierenMut = useMutation({
    mutationFn: () => objekteApi.vsKopieren(objektId!, selectedWj, Number(zielWj)),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['verteilerschluessel', objektId] })
      setKopierenOffen(false)
      setKopierenResult(`${data.kopiert} Werte nach WJ ${data.ziel_wj} kopiert.`)
      setTimeout(() => setKopierenResult(null), 5000)
    },
  })

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
        wirtschaftsjahr={selectedWj}
        onBack={() => setSelectedVs(null)}
      />
    )
  }

  if (isLoading) return <p className="text-gray-400">Laden…</p>

  const wjTabs = [{ id: 0, label: 'Zeitlos' }, ...wirtschaftsjahre.map(w => ({ id: w.jahr, label: `WJ ${w.jahr}` }))]

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Verteilerschlüssel</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">{vsList.length} Schlüssel</span>
          <button
            onClick={() => { setKopierenOffen(o => !o); setKopierenResult(null) }}
            className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50"
          >
            Ins nächste Jahr kopieren
          </button>
        </div>
      </div>

      {/* WJ-Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {wjTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => { setSelectedWj(tab.id); setSelectedVs(null) }}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              selectedWj === tab.id
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Hinweis bei WJ-spezifischer Ansicht */}
      {selectedWj > 0 && !kopierenOffen && (
        <div className="mb-4 bg-yellow-50 border border-yellow-200 text-yellow-800 rounded px-4 py-2 text-sm">
          Anzeige der Werte für <strong>WJ {selectedWj}</strong>. Einheiten mit 0 Werten haben noch keine WJ-spezifischen Einträge — ggf. aus Zeitlos kopieren.
        </div>
      )}

      {/* Kopieren-Panel */}
      {kopierenOffen && (
        <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm">
          <p className="font-medium text-blue-800 mb-2">
            VS-Werte kopieren ({selectedWj === 0 ? 'Zeitlos' : `WJ ${selectedWj}`} → WJ {zielWj})
          </p>
          <p className="text-blue-700 mb-3">
            Alle Schlüssel außer 140–145 (Verbrauch) werden kopiert. Vorhandene Werte im Ziel-WJ werden überschrieben.
          </p>
          <div className="flex items-center gap-3">
            <label className="text-gray-700">Ziel-Wirtschaftsjahr:</label>
            <input
              type="number"
              value={zielWj}
              onChange={e => setZielWj(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1 w-24 text-sm"
              min={2020}
              max={2099}
            />
            <button
              onClick={() => kopierenMut.mutate()}
              disabled={kopierenMut.isPending || !zielWj}
              className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {kopierenMut.isPending ? 'Kopiere…' : 'Kopieren'}
            </button>
            <button
              onClick={() => setKopierenOffen(false)}
              className="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-white"
            >
              Abbrechen
            </button>
          </div>
          {kopierenMut.isError && (
            <p className="mt-2 text-red-600">Fehler beim Kopieren.</p>
          )}
        </div>
      )}

      {/* Erfolgs-Toast */}
      {kopierenResult && (
        <div className="mb-4 bg-green-50 border border-green-200 text-green-800 rounded px-4 py-2 text-sm">
          {kopierenResult}
        </div>
      )}

      {/* Tabelle */}
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
