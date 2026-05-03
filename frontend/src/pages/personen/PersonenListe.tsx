import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { personenApi } from '../../api/personen'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { useObjektStore } from '../../stores/objekt'

const TYP_LABEL: Record<string, string> = {
  '100': 'Eigentümer',
  '200': 'Mieter',
  '300': 'Kreditor',
  '400': 'Sonstiges',
}

type SortKey = 'personennummer' | 'name' | 'typ_label' | 'email' | 'telefon'
type SortDir = 'asc' | 'desc'

interface Filters {
  personennummer: string
  name: string
  typ_label: string
  email: string
  telefon: string
}

const EMPTY_FILTERS: Filters = {
  personennummer: '',
  name: '',
  typ_label: '',
  email: '',
  telefon: '',
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

export function PersonenListe() {
  const navigate = useNavigate()
  const { selectedId: selectedObjektId, selectedName } = useObjektStore()
  const [sortKey, setSortKey] = useState<SortKey>('personennummer')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)

  const { data, isLoading } = useQuery({
    queryKey: ['personen', selectedObjektId ?? 'alle'],
    queryFn: () => personenApi.list(selectedObjektId ? { objekt: selectedObjektId } : undefined),
  })

  const rows = useMemo(
    () => (data ?? []).map(p => ({
      ...p,
      typ_label: TYP_LABEL[p.person_typ] ?? p.person_typ,
    })),
    [data],
  )

  const filtered = useMemo(() => rows.filter(r =>
    r.personennummer.toLowerCase().includes(filters.personennummer.toLowerCase()) &&
    r.name.toLowerCase().includes(filters.name.toLowerCase()) &&
    r.typ_label.toLowerCase().includes(filters.typ_label.toLowerCase()) &&
    (r.email ?? '').toLowerCase().includes(filters.email.toLowerCase()) &&
    (r.telefon ?? '').toLowerCase().includes(filters.telefon.toLowerCase()),
  ), [rows, filters])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    const av = (a[sortKey] ?? '').toLowerCase()
    const bv = (b[sortKey] ?? '').toLowerCase()
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

  const filterInput = (key: keyof Filters) => (
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
        <h1 className="text-2xl font-bold text-gray-900">Personen</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => navigate('/personen/import')}
            className="text-sm px-3 py-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            CSV Import
          </button>
          <Button onClick={() => navigate('/personen/neu')}>+ Neue Person</Button>
        </div>
      </div>

      {selectedObjektId && (
        <p className="text-sm text-gray-500">
          Gefiltert nach Objekt: <span className="font-medium text-gray-700">{selectedName}</span>
        </p>
      )}

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="space-y-2">
          <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className={thClass} onClick={() => handleSort('personennummer')}>
                    Nr. <SortIcon active={sortKey === 'personennummer'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('name')}>
                    Name <SortIcon active={sortKey === 'name'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('typ_label')}>
                    Typ <SortIcon active={sortKey === 'typ_label'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('email')}>
                    E-Mail <SortIcon active={sortKey === 'email'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('telefon')}>
                    Telefon <SortIcon active={sortKey === 'telefon'} dir={sortDir} />
                  </th>
                </tr>
                <tr className="bg-white border-b border-gray-100">
                  <td className="px-3 py-1">{filterInput('personennummer')}</td>
                  <td className="px-3 py-1">{filterInput('name')}</td>
                  <td className="px-3 py-1">{filterInput('typ_label')}</td>
                  <td className="px-3 py-1">{filterInput('email')}</td>
                  <td className="px-3 py-1">{filterInput('telefon')}</td>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      {hasFilters ? 'Keine Personen entsprechen den Filterkriterien.' : 'Keine Personen gefunden.'}
                    </td>
                  </tr>
                ) : (
                  sorted.map(p => (
                    <tr
                      key={p.id}
                      onClick={() => navigate(`/personen/${p.id}`)}
                      className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                    >
                      <td className="px-3 py-2.5 text-gray-500 tabular-nums">{p.personennummer}</td>
                      <td className="px-3 py-2.5 font-medium text-gray-800">
                        {p.name}
                        {p.ist_firma && <span className="ml-2 text-xs text-gray-400">[Firma]</span>}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge value={p.typ_label} />
                      </td>
                      <td className="px-3 py-2.5 text-gray-600">{p.email || '–'}</td>
                      <td className="px-3 py-2.5 text-gray-600">{p.telefon || '–'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Zählzeile */}
          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-gray-500">
              {hasFilters
                ? <><strong>{sorted.length}</strong> von <strong>{rows.length}</strong> Person{rows.length !== 1 ? 'en' : ''} angezeigt</>
                : <><strong>{rows.length}</strong> Person{rows.length !== 1 ? 'en' : ''}{selectedObjektId ? ' in dieser Liegenschaft' : ' gesamt'}</>
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
