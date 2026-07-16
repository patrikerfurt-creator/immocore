import React, { useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { useObjektStore } from '../../stores/objekt'

type ImportAktion = 'importieren' | 'ablehnen'
type VorschauRow = {
  zeile: number
  status: string
  aktion: ImportAktion
  fehler: string[]
  hinweis: string
  daten: Record<string, string | null>
}
type Vorschau = { rows: VorschauRow[]; ok_anzahl: number; duplikat_anzahl: number; fehler_anzahl: number; gesamt: number }
type ImportModus = 'ergaenzen' | 'neuimport'

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
  const [modus, setModus] = useState<ImportModus>('ergaenzen')
  const [importResult, setImportResult] = useState<{ angelegt: number; geloescht: number; fehler: string[] } | null>(null)
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
      setImportResult({ angelegt: 0, geloescht: 0, fehler: [data?.error ?? 'Fehler beim Lesen der Datei.'] })
    } finally {
      setImporting(false)
    }
  }

  const setAktion = (zeile: number, aktion: ImportAktion) =>
    setVorschau(prev => prev && {
      ...prev,
      rows: prev.rows.map(r => r.zeile === zeile ? { ...r, aktion } : r),
    })

  const setAlleAktion = (aktion: ImportAktion) =>
    setVorschau(prev => prev && {
      ...prev,
      // Fehlerzeilen sind nie importierbar und bleiben unangetastet
      rows: prev.rows.map(r => r.status === 'fehler' ? r : { ...r, aktion }),
    })

  const anzahlImport = vorschau
    ? (modus === 'neuimport'
        // Neuimport ersetzt das Objekt komplett → alle fehlerfreien Zeilen zählen
        ? vorschau.rows.filter(r => r.status !== 'fehler').length
        : vorschau.rows.filter(r => r.status !== 'fehler' && r.aktion === 'importieren').length)
    : 0

  const handleImportBestaetigen = async () => {
    if (!vorschau) return
    if (modus === 'neuimport') {
      const ok = window.confirm(
        `Kompletter Neuimport für Objekt "${selectedName}":\n\n` +
        `ALLE vorhandenen Einheiten dieses Objekts werden gelöscht und durch ` +
        `${anzahlImport} neue ersetzt.\n\n` +
        `Das ist nur möglich, wenn an den vorhandenen Einheiten keine Daten ` +
        `(Eigentümer, Verträge, Abrechnungen …) hängen.\n\nFortfahren?`
      )
      if (!ok) return
    }
    setImporting(true)
    setImportResult(null)
    try {
      const result = await objekteApi.csvImportEinheiten(vorschau.rows, modus)
      setImportResult({ angelegt: result.angelegt, geloescht: result.geloescht ?? 0, fehler: result.fehler ?? [] })
      setVorschau(null)
      setModus('ergaenzen')
      qc.invalidateQueries({ queryKey: ['einheiten', selectedObjektId] })
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { fehler?: string[]; error?: string; gruende?: string[] } } })?.response?.data
      let msgs: string[]
      if (data?.gruende?.length) {
        msgs = [data.error ?? 'Neuimport nicht möglich.', ...data.gruende.map(g => `• ${g}`)]
      } else if (data?.fehler?.length) {
        msgs = data.fehler
      } else {
        msgs = [data?.error ?? 'Fehler beim Import.']
      }
      setImportResult({ angelegt: 0, geloescht: 0, fehler: msgs })
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
            <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer select-none ml-auto">
              <input
                type="checkbox"
                checked={modus === 'neuimport'}
                onChange={e => setModus(e.target.checked ? 'neuimport' : 'ergaenzen')}
                className="rounded border-gray-300 text-red-600 focus:ring-red-400"
              />
              Kompletter Neuimport (alle Einheiten löschen)
            </label>
          </div>

          {modus === 'neuimport' && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
              <strong>Achtung:</strong> Beim Import werden zuerst <strong>alle vorhandenen Einheiten dieses Objekts gelöscht</strong>.
              Das gelingt nur, wenn keine abhängigen Daten (Eigentümer, Verträge, Abrechnungen …) daran hängen — sonst wird der Import abgebrochen und nichts verändert.
            </div>
          )}
          <p className="text-xs text-gray-400 -mt-2">
            Spalten: Objektnummer; Eingang; Flächennummer; Bez. Einheit; Einheit-Typ (100/200/300/400); Lage
          </p>

          {/* Import-Ergebnis */}
          {importResult && (
            <div className={`rounded-lg border p-3 space-y-1 ${importResult.fehler.length ? 'bg-amber-50 border-amber-200' : 'bg-green-50 border-green-200'}`}>
              <p className="text-sm font-medium text-gray-700">
                Import abgeschlossen: <strong>{importResult.angelegt}</strong> Einheit{importResult.angelegt !== 1 ? 'en' : ''} angelegt
                {importResult.geloescht > 0 && <>, <strong>{importResult.geloescht}</strong> gelöscht</>}
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
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-sm font-semibold text-gray-800">
                  Vorschau: {vorschau.gesamt} Zeilen — <span className="text-green-700">{vorschau.ok_anzahl} neu</span>
                  {vorschau.duplikat_anzahl > 0 && <>, <span className="text-amber-600">{vorschau.duplikat_anzahl} bereits vorhanden</span></>}
                  {vorschau.fehler_anzahl > 0 && <>, <span className="text-red-600">{vorschau.fehler_anzahl} Fehler</span></>}
                </p>
                <div className="flex items-center gap-2">
                  {modus === 'ergaenzen' && (
                    <>
                      <button
                        type="button"
                        onClick={() => setAlleAktion('importieren')}
                        className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50"
                      >
                        Alle importieren
                      </button>
                      <button
                        type="button"
                        onClick={() => setAlleAktion('ablehnen')}
                        className="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50"
                      >
                        Alle ablehnen
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => setVorschau(null)}
                    className="text-xs text-gray-500 hover:text-gray-700 underline"
                  >
                    Abbrechen
                  </button>
                </div>
              </div>

              {modus === 'neuimport' && (
                <p className="text-xs text-red-700">
                  Neuimport: Alle vorhandenen Einheiten werden gelöscht und durch <strong>alle {anzahlImport}</strong> fehlerfreien Zeilen ersetzt. Die Einzel-Auswahl unten ist dabei inaktiv.
                </p>
              )}

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
                      <th className="px-2 py-1.5 text-left font-medium text-gray-600 w-44">Aktion / Hinweis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vorschau.rows.map(row => {
                      const isFehler = row.status === 'fehler'
                      const isDup = row.status === 'duplikat'
                      const rowBg = isFehler ? 'bg-red-50' : isDup ? 'bg-amber-50' : ''
                      return (
                        <tr key={row.zeile} className={`border-t ${rowBg}`}>
                          <td className="px-2 py-1 text-gray-500">{row.zeile}</td>
                          <td className="px-2 py-1 whitespace-nowrap">
                            {isFehler
                              ? <span className="text-red-600 font-medium">Fehler</span>
                              : isDup
                                ? <span className="text-amber-600 font-medium">Bereits vorhanden</span>
                                : <span className="text-green-700">Neu</span>}
                          </td>
                          <td className="px-2 py-1 text-gray-600">{row.daten.flaechennummer || '–'}</td>
                          <td className="px-2 py-1 text-gray-800">{row.daten.einheit_nr || '–'}</td>
                          <td className="px-2 py-1 text-gray-600">{row.daten.einheit_typ || '–'}</td>
                          <td className="px-2 py-1 text-gray-600">{row.daten.lage || '–'}</td>
                          <td className="px-2 py-1">
                            {isFehler ? (
                              <span className="text-red-600">{row.fehler.join('; ')}</span>
                            ) : modus === 'neuimport' ? (
                              <span className="text-green-700">wird importiert</span>
                            ) : (
                              <div className="space-y-0.5">
                                <div className="flex rounded overflow-hidden border border-gray-200 w-fit">
                                  <button
                                    type="button"
                                    onClick={() => setAktion(row.zeile, 'importieren')}
                                    className={`px-2 py-0.5 transition-colors ${row.aktion === 'importieren' ? 'bg-green-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                                  >
                                    Importieren
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setAktion(row.zeile, 'ablehnen')}
                                    className={`px-2 py-0.5 border-l border-gray-200 transition-colors ${row.aktion === 'ablehnen' ? 'bg-red-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                                  >
                                    Ablehnen
                                  </button>
                                </div>
                                {row.hinweis && <p className="text-amber-600">{row.hinweis}</p>}
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleImportBestaetigen}
                  disabled={importing || anzahlImport === 0}
                  className="px-4 py-2 rounded bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {importing
                    ? 'Importiere…'
                    : modus === 'neuimport'
                      ? `Neuimport: ${anzahlImport} Einheit${anzahlImport !== 1 ? 'en' : ''} (alte löschen)`
                      : `${anzahlImport} Einheit${anzahlImport !== 1 ? 'en' : ''} importieren`}
                </button>
              </div>
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
