import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import type { ObjektList } from '../../types'

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

export function ObjekteListe() {
  const { data, isLoading } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const [sortKey, setSortKey] = useState<SortKey>('objektnummer')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)

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

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const setFilter = (key: keyof Filters, value: string) =>
    setFilters(prev => ({ ...prev, [key]: value }))

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
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Objekte</h1>
        <Link
          to="/prozesse?typ=objekt_anlegen"
          className="bg-primary-600 text-white px-4 py-2 rounded text-sm hover:bg-primary-700 transition-colors"
        >
          + Objekt anlegen
        </Link>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="space-y-2">
          <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
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
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      {hasFilters ? 'Keine Objekte entsprechen den Filterkriterien.' : 'Noch keine Objekte vorhanden.'}
                    </td>
                  </tr>
                ) : (
                  sorted.map(o => (
                    <tr key={o.id} className="border-b border-gray-100 hover:bg-gray-50">
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
