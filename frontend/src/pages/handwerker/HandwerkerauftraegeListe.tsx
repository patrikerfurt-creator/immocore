import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { handwerkerApi } from '../../api/handwerker'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Input } from '../../components/ui/Input'
import type { HandwerkerauftragStatus } from '../../types'
import { HWA_STATUS_LABEL, HWA_STATUS_OPTIONEN, formatDatum, formatGeld } from './shared'

const PRIORITAET_OPTIONEN = [
  { value: 'niedrig', label: 'Niedrig' },
  { value: 'normal', label: 'Normal' },
  { value: 'hoch', label: 'Hoch' },
]

export function HandwerkerauftraegeListe() {
  const [searchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState<Set<HandwerkerauftragStatus>>(new Set())
  const [objektFilter, setObjektFilter] = useState(searchParams.get('objekt') ?? '')
  const [kreditorFilter, setKreditorFilter] = useState('')
  const [prioritaetFilter, setPrioritaetFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: handwerker } = useQuery({
    queryKey: ['handwerker-kreditoren-filter'],
    queryFn: () => handwerkerApi.kreditorenHandwerker(),
  })

  const params: Record<string, string | number> = { page, page_size: pageSize }
  if (statusFilter.size > 0) params.status = Array.from(statusFilter).join(',')
  if (objektFilter) params.objekt = objektFilter
  if (kreditorFilter) params.kreditor = kreditorFilter
  if (prioritaetFilter) params.prioritaet = prioritaetFilter
  if (search) params.search = search

  const { data, isLoading } = useQuery({
    queryKey: ['handwerkerauftraege', statusFilter.size, Array.from(statusFilter).join(','), objektFilter, kreditorFilter, prioritaetFilter, search, page],
    queryFn: () => handwerkerApi.list(params),
  })

  function toggleStatus(s: HandwerkerauftragStatus) {
    setStatusFilter(prev => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
    setPage(1)
  }

  const anzahlSeiten = data ? Math.max(1, Math.ceil(data.count / pageSize)) : 1

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Handwerkeraufträge</h1>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {HWA_STATUS_OPTIONEN.map(o => (
            <button
              key={o.value}
              type="button"
              onClick={() => toggleStatus(o.value)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                statusFilter.has(o.value)
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={objektFilter}
            onChange={e => { setObjektFilter(e.target.value); setPage(1) }}
          >
            <option value="">Alle Objekte</option>
            {objekte?.map(o => (
              <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
            ))}
          </select>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={kreditorFilter}
            onChange={e => { setKreditorFilter(e.target.value); setPage(1) }}
          >
            <option value="">Alle Handwerker</option>
            {handwerker?.map(k => (
              <option key={k.id} value={k.id}>{k.name}</option>
            ))}
          </select>
          <select
            className="rounded border border-gray-300 px-3 py-2 text-sm"
            value={prioritaetFilter}
            onChange={e => { setPrioritaetFilter(e.target.value); setPage(1) }}
          >
            <option value="">Alle Prioritäten</option>
            {PRIORITAET_OPTIONEN.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <div className="flex-1 min-w-[200px]">
            <Input
              placeholder="Suche (Titel, Beschreibung, Nummer)…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <>
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Nummer</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Titel</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Objekt</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Handwerker</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Priorität</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Kosten</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Erstellt am</th>
                </tr>
              </thead>
              <tbody>
                {data?.results.map(a => (
                  <tr key={a.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link to={`/handwerker/auftraege/${a.id}`} className="text-primary-600 hover:underline font-mono text-xs">
                        {a.nummer}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">{a.titel}</td>
                    <td className="px-4 py-3 text-gray-600">{a.objekt_bezeichnung ?? '–'}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {a.kreditor_name}
                      {a.kreditor_gewerke_bezeichnung && (
                        <span className="text-gray-400"> ({a.kreditor_gewerke_bezeichnung})</span>
                      )}
                    </td>
                    <td className="px-4 py-3"><Badge value={a.status} label={HWA_STATUS_LABEL[a.status]} /></td>
                    <td className="px-4 py-3"><Badge value={a.prioritaet} /></td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">{formatGeld(a.geschaetzte_kosten)}</td>
                    <td className="px-4 py-3 text-gray-600">{formatDatum(a.erstellt_am)}</td>
                  </tr>
                ))}
                {data?.results.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                      Keine Handwerkeraufträge gefunden.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {data && data.count > pageSize && (
            <div className="flex items-center justify-between mt-3 text-sm text-gray-600">
              <span>
                Seite {page} von {anzahlSeiten} ({data.count} Aufträge)
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={!data.previous}
                  className="px-3 py-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                >
                  ← Zurück
                </button>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={!data.next}
                  className="px-3 py-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                >
                  Weiter →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
