import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { ObjektList, FolgejahrPreviewEintrag, FolgejahrCommitEintrag } from '../../types'

type SortKey = 'objektnummer' | 'bezeichnung' | 'objekt_typ' | 'anschrift' | 'status'
type SortDir = 'asc' | 'desc'

interface Filters {
  objektnummer: string
  bezeichnung: string
  objekt_typ: string
  anschrift: string
  status: string
}

const EMPTY_FILTERS: Filters = {
  objektnummer: '', bezeichnung: '', objekt_typ: '', anschrift: '', status: '',
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

type ObjektRow = ObjektList & { anschrift: string }

// ── Preview-Dialog ─────────────────────────────────────────────────────
function FolgejahrPreviewDialog({
  ergebnisse,
  onCommit,
  onAbort,
  isLoading,
}: {
  ergebnisse: FolgejahrPreviewEintrag[]
  onCommit: (ids: string[]) => void
  onAbort: () => void
  isLoading: boolean
}) {
  const viable = ergebnisse.filter(e => e.status === 'ok').map(e => e.objekt_id)
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="px-5 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">Nächstes Wirtschaftsjahr eröffnen — Vorschau</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {viable.length} von {ergebnisse.length} Objekt{ergebnisse.length !== 1 ? 'en' : ''} können ein Folgejahr erhalten.
          </p>
        </div>
        <div className="overflow-y-auto flex-1 p-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-xs text-gray-600">
                <th className="text-left px-3 py-2 font-medium">Nr.</th>
                <th className="text-left px-3 py-2 font-medium">Bezeichnung</th>
                <th className="text-left px-3 py-2 font-medium">Letztes WJ</th>
                <th className="text-left px-3 py-2 font-medium">Folgejahr</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {ergebnisse.map(e => (
                <tr key={e.objekt_id} className="border-t border-gray-100">
                  <td className="px-3 py-2 font-mono text-gray-500">{e.objekt_nr}</td>
                  <td className="px-3 py-2 text-gray-800">{e.bezeichnung}</td>
                  <td className="px-3 py-2 text-gray-600">
                    {e.letztes_wj ? `${e.letztes_wj.jahr}` : '—'}
                  </td>
                  <td className="px-3 py-2 text-gray-800 font-medium">
                    {e.folgejahr ?? '—'}
                  </td>
                  <td className="px-3 py-2">
                    {e.status === 'ok' ? (
                      <span className="text-green-700 font-medium">Möglich</span>
                    ) : (
                      <span className="text-red-600 text-xs" title={e.fehler ?? ''}>
                        Nicht möglich
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-5 py-3 border-t border-gray-200 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onAbort} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button
            size="sm"
            onClick={() => onCommit(viable)}
            disabled={isLoading || viable.length === 0}
          >
            {isLoading ? 'Wird eröffnet…' : `${viable.length} Folgejahr${viable.length !== 1 ? 'e' : ''} eröffnen`}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Ergebnis-Dialog ────────────────────────────────────────────────────
function FolgejahrErgebnisDialog({
  ergebnisse,
  onClose,
}: {
  ergebnisse: FolgejahrCommitEintrag[]
  onClose: () => void
}) {
  const ok  = ergebnisse.filter(e => e.status === 'ok').length
  const err = ergebnisse.filter(e => e.status === 'fehler').length
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg">
        <div className="px-5 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">Wirtschaftsjahre eröffnet</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {ok} erfolgreich, {err} Fehler
          </p>
        </div>
        <div className="p-4 space-y-2 max-h-72 overflow-y-auto">
          {ergebnisse.map((e, i) => (
            <div key={i} className={`flex items-start gap-2 text-sm ${e.status === 'ok' ? 'text-green-700' : 'text-red-600'}`}>
              <span className="font-medium shrink-0">{e.status === 'ok' ? '✓' : '✗'}</span>
              <span>
                {e.bezeichnung ?? e.objekt_id}
                {e.wj_jahr ? ` → WJ ${e.wj_jahr}` : ''}
                {e.fehler ? `: ${e.fehler}` : ''}
              </span>
            </div>
          ))}
        </div>
        <div className="px-5 py-3 border-t border-gray-200 flex justify-end">
          <Button size="sm" onClick={onClose}>Schließen</Button>
        </div>
      </div>
    </div>
  )
}

// ── Haupt-Komponente ───────────────────────────────────────────────────
export function ObjekteListe() {
  const { data, isLoading } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const [sortKey, setSortKey] = useState<SortKey>('objektnummer')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewData, setPreviewData] = useState<FolgejahrPreviewEintrag[] | null>(null)
  const [commitData, setCommitData] = useState<FolgejahrCommitEintrag[] | null>(null)

  const rows = useMemo<ObjektRow[]>(
    () => (data ?? []).map(o => ({ ...o, anschrift: `${o.strasse}, ${o.plz} ${o.ort}` })),
    [data],
  )

  const filtered = useMemo(() => rows.filter(r =>
    r.objektnummer.toLowerCase().includes(filters.objektnummer.toLowerCase()) &&
    r.bezeichnung.toLowerCase().includes(filters.bezeichnung.toLowerCase()) &&
    r.objekt_typ.toLowerCase().includes(filters.objekt_typ.toLowerCase()) &&
    r.anschrift.toLowerCase().includes(filters.anschrift.toLowerCase()) &&
    r.status.toLowerCase().includes(filters.status.toLowerCase()),
  ), [rows, filters])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    const av = a[sortKey].toLowerCase()
    const bv = b[sortKey].toLowerCase()
    const cmp = av.localeCompare(bv, 'de', { numeric: true })
    return sortDir === 'asc' ? cmp : -cmp
  }), [filtered, sortKey, sortDir])

  const allFilteredIds = useMemo(() => sorted.map(o => o.id), [sorted])
  const allSelected = allFilteredIds.length > 0 && allFilteredIds.every(id => selected.has(id))
  const someSelected = allFilteredIds.some(id => selected.has(id))

  const previewMutation = useMutation({
    mutationFn: (ids: string[]) => wirtschaftsjahreApi.folgejahrPreview(ids),
    onSuccess: data => setPreviewData(data.ergebnisse),
  })

  const commitMutation = useMutation({
    mutationFn: (ids: string[]) => wirtschaftsjahreApi.folgejahrCommit(ids),
    onSuccess: data => {
      setPreviewData(null)
      setCommitData(data.ergebnisse)
      setSelected(new Set())
    },
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const setFilter = (key: keyof Filters, value: string) =>
    setFilters(prev => ({ ...prev, [key]: value }))

  const toggleRow = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleAll = () => {
    if (allSelected) {
      setSelected(prev => {
        const next = new Set(prev)
        allFilteredIds.forEach(id => next.delete(id))
        return next
      })
    } else {
      setSelected(prev => new Set([...prev, ...allFilteredIds]))
    }
  }

  const selectedIds = [...selected]
  const hasFilters = Object.values(filters).some(v => v !== '')

  const thClass = 'text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap cursor-pointer select-none hover:bg-gray-100'

  const fi = (key: keyof Filters) => (
    <input
      type="text"
      value={filters[key]}
      onChange={e => setFilter(key, e.target.value)}
      placeholder="Filter…"
      className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-400"
    />
  )

  return (
    <div className="space-y-4">
      {previewData && (
        <FolgejahrPreviewDialog
          ergebnisse={previewData}
          onCommit={ids => commitMutation.mutate(ids)}
          onAbort={() => setPreviewData(null)}
          isLoading={commitMutation.isPending}
        />
      )}
      {commitData && (
        <FolgejahrErgebnisDialog
          ergebnisse={commitData}
          onClose={() => setCommitData(null)}
        />
      )}

      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Objekte</h1>
        <div className="flex items-center gap-2">
          {someSelected && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => previewMutation.mutate(selectedIds)}
              disabled={previewMutation.isPending}
            >
              {previewMutation.isPending
                ? 'Prüfe…'
                : `Nächstes WJ eröffnen (${selectedIds.length})`}
            </Button>
          )}
          <Link
            to="/prozesse?typ=objekt_anlegen"
            className="bg-primary-600 text-white px-4 py-2 rounded text-sm hover:bg-primary-700 transition-colors"
          >
            + Objekt anlegen
          </Link>
        </div>
      </div>

      {previewMutation.isError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          Fehler bei der Vorschau. Bitte erneut versuchen.
        </div>
      )}

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="space-y-2">
          <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 w-8">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={el => { if (el) el.indeterminate = someSelected && !allSelected }}
                      onChange={toggleAll}
                      className="rounded border-gray-300 text-primary-600"
                    />
                  </th>
                  <th className={thClass} onClick={() => handleSort('objektnummer')}>
                    Nr. <SortIcon active={sortKey === 'objektnummer'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('bezeichnung')}>
                    Bezeichnung <SortIcon active={sortKey === 'bezeichnung'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('objekt_typ')}>
                    Typ <SortIcon active={sortKey === 'objekt_typ'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('anschrift')}>
                    Hauptanschrift <SortIcon active={sortKey === 'anschrift'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('status')}>
                    Status <SortIcon active={sortKey === 'status'} dir={sortDir} />
                  </th>
                </tr>
                <tr className="bg-white border-b border-gray-100">
                  <td className="px-3 py-1" />
                  <td className="px-3 py-1">{fi('objektnummer')}</td>
                  <td className="px-3 py-1">{fi('bezeichnung')}</td>
                  <td className="px-3 py-1">{fi('objekt_typ')}</td>
                  <td className="px-3 py-1">{fi('anschrift')}</td>
                  <td className="px-3 py-1">{fi('status')}</td>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      {hasFilters ? 'Keine Objekte entsprechen den Filterkriterien.' : 'Noch keine Objekte vorhanden.'}
                    </td>
                  </tr>
                ) : (
                  sorted.map(o => (
                    <tr
                      key={o.id}
                      className={`border-b border-gray-100 hover:bg-gray-50 ${selected.has(o.id) ? 'bg-primary-50' : ''}`}
                    >
                      <td className="px-3 py-2.5">
                        <input
                          type="checkbox"
                          checked={selected.has(o.id)}
                          onChange={() => toggleRow(o.id)}
                          className="rounded border-gray-300 text-primary-600"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-gray-500 font-mono">{o.objektnummer}</td>
                      <td className="px-3 py-2.5">
                        <Link to={`/objekte/${o.id}`} className="text-primary-600 hover:underline font-medium">
                          {o.bezeichnung}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5"><Badge value={o.objekt_typ} /></td>
                      <td className="px-3 py-2.5 text-gray-700">{o.anschrift}</td>
                      <td className="px-3 py-2.5"><Badge value={o.status} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-gray-500">
              {hasFilters
                ? <><strong>{sorted.length}</strong> von <strong>{rows.length}</strong> Objekt{rows.length !== 1 ? 'en' : ''} angezeigt</>
                : <><strong>{rows.length}</strong> Objekt{rows.length !== 1 ? 'e' : ''} gesamt</>
              }
              {someSelected && (
                <span className="ml-3 text-primary-600 font-medium">{selectedIds.length} ausgewählt</span>
              )}
            </p>
            {hasFilters && (
              <button
                type="button"
                onClick={() => setFilters(EMPTY_FILTERS)}
                className="text-xs text-primary-600 hover:text-primary-700 underline"
              >
                Filter zurücksetzen
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
