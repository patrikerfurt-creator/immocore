import React, { useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { useObjektStore } from '../../stores/objekt'

type VorschauRow = { zeile: number; status: string; fehler: string[]; daten: Record<string, string | null> }
type Vorschau = { rows: VorschauRow[]; ok_anzahl: number; fehler_anzahl: number; gesamt: number }

type SortKey = 'flaechennummer' | 'einheit_nr' | 'einheit_typ' | 'lage' | 'eingang_bezeichnung' | 'eigentuemer'
type SortDir = 'asc' | 'desc'

interface Filters {
  flaechennummer: string
  einheit_nr: string
  einheit_typ: string
  lage: string
  eingang_bezeichnung: string
  eigentuemer: string
}

const EMPTY_FILTERS: Filters = {
  flaechennummer: '',
  einheit_nr: '',
  einheit_typ: '',
  lage: '',
  eingang_bezeichnung: '',
  eigentuemer: '',
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

export function EinheitenPage() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const { selectedId: selectedObjektId, selectedName } = useObjektStore()
  const [vorschau, setVorschau] = useState<Vorschau | null>(null)
  const [importResult, setImportResult] = useState<{ angelegt: number; fehler: string[] } | null>(null)
  const [importing, setImporting] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('flaechennummer')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [editEinheitId, setEditEinheitId] = useState<string | null>(null)
  const [editPersonId, setEditPersonId] = useState<string>('')

  const { data: einheiten = [], isLoading: loadingE } = useQuery({
    queryKey: ['einheiten', selectedObjektId],
    queryFn: () => objekteApi.listEinheiten({ objekt: selectedObjektId! }),
    enabled: !!selectedObjektId,
  })

  const { data: evs = [], isLoading: loadingEV } = useQuery({
    queryKey: ['eigentumsverhaeltnisse', 'objekt', selectedObjektId],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ objekt: selectedObjektId!, aktiv: 'true' }),
    enabled: !!selectedObjektId,
  })

  const { data: personen = [] } = useQuery({
    queryKey: ['personen-eigentuemer'],
    queryFn: () => personenApi.list({ person_typ: '100' }),
    enabled: !!selectedObjektId,
  })

  const updateEvMut = useMutation({
    mutationFn: ({ evId, personId }: { evId: string; personId: string }) =>
      personenApi.updateEigentumsverhaeltnis(evId, { person: personId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['eigentumsverhaeltnisse', 'objekt', selectedObjektId] })
      setEditEinheitId(null)
    },
  })

  const evByEinheit = useMemo(
    () => new Map(evs.map(ev => [ev.einheit, ev])),
    [evs],
  )

  const rows = useMemo(
    () => einheiten.map(e => ({
      ...e,
      eigentuemer: evByEinheit.get(e.id)?.person_name ?? '',
    })),
    [einheiten, evByEinheit],
  )

  const filtered = useMemo(() => rows.filter(r =>
    (r.flaechennummer ?? '').toLowerCase().includes(filters.flaechennummer.toLowerCase()) &&
    r.einheit_nr.toLowerCase().includes(filters.einheit_nr.toLowerCase()) &&
    r.einheit_typ.toLowerCase().includes(filters.einheit_typ.toLowerCase()) &&
    r.lage.toLowerCase().includes(filters.lage.toLowerCase()) &&
    (r.eingang_bezeichnung ?? '').toLowerCase().includes(filters.eingang_bezeichnung.toLowerCase()) &&
    r.eigentuemer.toLowerCase().includes(filters.eigentuemer.toLowerCase()),
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

  const handleVorlage = async () => {
    const blob = await objekteApi.csvVorlageEinheiten(selectedObjektId ?? undefined)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'einheiten_vorlage.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setImporting(true)
    setImportResult(null)
    setVorschau(null)
    try {
      const result = await objekteApi.csvVorschauEinheiten(file)
      setVorschau(result)
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { error?: string } } })?.response?.data
      setImportResult({ angelegt: 0, fehler: [data?.error ?? 'Fehler beim Lesen der Datei.'] })
    } finally {
      setImporting(false)
    }
  }

  const handleImportBestaetigen = async () => {
    if (!vorschau) return
    setImporting(true)
    setImportResult(null)
    try {
      const result = await objekteApi.csvImportEinheiten(vorschau.rows)
      setImportResult({ angelegt: result.angelegt, fehler: result.fehler ?? [] })
      setVorschau(null)
      qc.invalidateQueries({ queryKey: ['einheiten', selectedObjektId] })
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { fehler?: string[]; error?: string } } })?.response?.data
      const msgs = data?.fehler?.length ? data.fehler : [data?.error ?? 'Fehler beim Import.']
      setImportResult({ angelegt: 0, fehler: msgs })
    } finally {
      setImporting(false)
    }
  }

  const isLoading = loadingE || loadingEV

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
      <h1 className="text-2xl font-bold text-gray-900">Einheiten</h1>

      {!selectedObjektId ? (
        <p className="text-sm text-gray-500">Bitte wähle zuerst ein Objekt in der Seitenleiste aus.</p>
      ) : (
        <p className="text-sm text-gray-500">Objekt: <span className="font-medium text-gray-700">{selectedName}</span></p>
      )}

      {selectedObjektId && (
        <>
          {/* Import-Leiste */}
          <div className="flex items-center gap-3 bg-gray-50 rounded-lg border border-gray-200 px-4 py-3">
            <button
              type="button"
              onClick={handleVorlage}
              className="text-sm text-primary-600 hover:text-primary-700 underline"
            >
              CSV-Vorlage herunterladen
            </button>
            <span className="text-gray-300">|</span>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={importing}
              className="text-sm px-3 py-1.5 rounded bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {importing ? 'Prüfe…' : 'CSV importieren'}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={handleFileSelect}
            />
            <span className="text-xs text-gray-400">
              Spalten: Objektnummer; Eingang; Flächennummer; Bez. Einheit; Einheit-Typ (100/200/300/400); Lage
            </span>
          </div>

          {/* Import-Ergebnis */}
          {importResult && (
            <div className={`rounded-lg border p-3 space-y-1 ${importResult.fehler.length ? 'bg-amber-50 border-amber-200' : 'bg-green-50 border-green-200'}`}>
              <p className="text-sm font-medium text-gray-700">
                Import abgeschlossen: <strong>{importResult.angelegt}</strong> Einheit{importResult.angelegt !== 1 ? 'en' : ''} angelegt
                {importResult.fehler.length > 0 && <>, <strong>{importResult.fehler.length}</strong> Fehler</>}
              </p>
              {importResult.fehler.map((f, i) => (
                <p key={i} className="text-xs text-red-600">• {f}</p>
              ))}
            </div>
          )}

          {/* Vorschau */}
          {vorschau && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-800">
                  Vorschau: {vorschau.gesamt} Zeilen — <span className="text-green-700">{vorschau.ok_anzahl} ok</span>
                  {vorschau.fehler_anzahl > 0 && <>, <span className="text-red-600">{vorschau.fehler_anzahl} Fehler</span></>}
                </p>
                <button
                  type="button"
                  onClick={() => setVorschau(null)}
                  className="text-xs text-gray-500 hover:text-gray-700 underline"
                >
                  Abbrechen
                </button>
              </div>

              <div className="overflow-x-auto rounded border border-blue-200 bg-white max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Zeile</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Status</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Fl-Nr.</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Bez. Einheit</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Typ</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Lage</th>
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600">Fehler</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vorschau.rows.map(row => (
                      <tr key={row.zeile} className={`border-t ${row.status === 'fehler' ? 'bg-red-50' : ''}`}>
                        <td className="px-2 py-1 text-gray-500">{row.zeile}</td>
                        <td className="px-2 py-1">
                          {row.status === 'fehler'
                            ? <span className="text-red-600 font-medium">Fehler</span>
                            : <span className="text-green-700">OK</span>}
                        </td>
                        <td className="px-2 py-1 text-gray-600">{row.daten.flaechennummer || '–'}</td>
                        <td className="px-2 py-1 text-gray-800">{row.daten.einheit_nr || '–'}</td>
                        <td className="px-2 py-1 text-gray-600">{row.daten.einheit_typ || '–'}</td>
                        <td className="px-2 py-1 text-gray-600">{row.daten.lage || '–'}</td>
                        <td className="px-2 py-1 text-red-600">{row.fehler.join('; ') || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {vorschau.ok_anzahl > 0 && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={handleImportBestaetigen}
                    disabled={importing}
                    className="px-4 py-2 rounded bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                  >
                    {importing ? 'Importiere…' : `${vorschau.ok_anzahl} Einheit${vorschau.ok_anzahl !== 1 ? 'en' : ''} importieren`}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Tabelle */}
          {isLoading ? (
            <p className="text-sm text-gray-400">Laden…</p>
          ) : einheiten.length === 0 ? (
            <p className="text-sm text-gray-400">Keine Einheiten vorhanden. Bitte CSV importieren.</p>
          ) : (
            <div className="space-y-2">
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className={thClass} onClick={() => handleSort('flaechennummer')}>
                        Fl-Nr. <SortIcon active={sortKey === 'flaechennummer'} dir={sortDir} />
                      </th>
                      <th className={thClass} onClick={() => handleSort('einheit_nr')}>
                        Bez. Einheit <SortIcon active={sortKey === 'einheit_nr'} dir={sortDir} />
                      </th>
                      <th className={thClass} onClick={() => handleSort('einheit_typ')}>
                        Typ <SortIcon active={sortKey === 'einheit_typ'} dir={sortDir} />
                      </th>
                      <th className={thClass} onClick={() => handleSort('lage')}>
                        Lage <SortIcon active={sortKey === 'lage'} dir={sortDir} />
                      </th>
                      <th className={thClass} onClick={() => handleSort('eingang_bezeichnung')}>
                        Eingang <SortIcon active={sortKey === 'eingang_bezeichnung'} dir={sortDir} />
                      </th>
                      <th className={thClass} onClick={() => handleSort('eigentuemer')}>
                        Eigentümer <SortIcon active={sortKey === 'eigentuemer'} dir={sortDir} />
                      </th>
                    </tr>
                    <tr className="bg-white border-b border-gray-100">
                      <td className="px-3 py-1">{filterInput('flaechennummer')}</td>
                      <td className="px-3 py-1">{filterInput('einheit_nr')}</td>
                      <td className="px-3 py-1">{filterInput('einheit_typ')}</td>
                      <td className="px-3 py-1">{filterInput('lage')}</td>
                      <td className="px-3 py-1">{filterInput('eingang_bezeichnung')}</td>
                      <td className="px-3 py-1">{filterInput('eigentuemer')}</td>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-6 text-center text-sm text-gray-400">
                          Keine Einheiten entsprechen den Filterkriterien.
                        </td>
                      </tr>
                    ) : (
                      sorted.map(e => (
                        <tr key={e.id} className="border-t border-gray-100 hover:bg-gray-50">
                          <td className="px-3 py-2.5 text-gray-500">{e.flaechennummer || '–'}</td>
                          <td className="px-3 py-2.5 font-medium text-gray-800">{e.einheit_nr}</td>
                          <td className="px-3 py-2.5 text-gray-600">{e.einheit_typ || '–'}</td>
                          <td className="px-3 py-2.5 text-gray-600">{e.lage}</td>
                          <td className="px-3 py-2.5 text-gray-600">{e.eingang_bezeichnung || '–'}</td>
                          <td className="px-3 py-2.5 text-gray-800">
                            {editEinheitId === e.id ? (
                              <div className="flex items-center gap-1">
                                <select
                                  value={editPersonId}
                                  onChange={ev => setEditPersonId(ev.target.value)}
                                  className="text-sm border border-primary-400 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-500"
                                  autoFocus
                                >
                                  <option value="">— keine —</option>
                                  {personen.map(p => (
                                    <option key={p.id} value={p.id}>{p.name}</option>
                                  ))}
                                </select>
                                <button
                                  onClick={() => {
                                    const ev = evByEinheit.get(e.id)
                                    if (ev && editPersonId) updateEvMut.mutate({ evId: ev.id, personId: editPersonId })
                                  }}
                                  disabled={!editPersonId || updateEvMut.isPending}
                                  className="text-xs px-2 py-1 bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
                                >
                                  ✓
                                </button>
                                <button
                                  onClick={() => setEditEinheitId(null)}
                                  className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
                                >
                                  ✕
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-2 group">
                                <span>{e.eigentuemer || <span className="text-gray-400 italic text-xs">–</span>}</span>
                                <button
                                  onClick={() => {
                                    const ev = evByEinheit.get(e.id)
                                    setEditEinheitId(e.id)
                                    setEditPersonId(ev?.person ?? '')
                                  }}
                                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-primary-600 text-xs transition-opacity"
                                  title="Eigentümer ändern"
                                >
                                  ✏
                                </button>
                              </div>
                            )}
                          </td>
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
                    ? <><strong>{sorted.length}</strong> von <strong>{einheiten.length}</strong> Einheiten angezeigt</>
                    : <><strong>{einheiten.length}</strong> Einheit{einheiten.length !== 1 ? 'en' : ''} gesamt</>
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
        </>
      )}
    </div>
  )
}
