import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { Abrechnungsart, Einheit, EigentumsVerhaeltnis, PersonList } from '../../types'
import type { VertraegeVorschauResponse } from '../../api/personen'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { useObjektStore } from '../../stores/objekt'

// Einheit-Typ → dreistellige Kennzahl
const TYP_CODE: Record<string, string> = {
  Wohnung: '100',
  Gewerbe: '200',
  Stellplatz: '300',
  Sonstiges: '400',
}

// ────────────────────────────────────────────────────────────────────────────
// Modal-Typen
// ────────────────────────────────────────────────────────────────────────────
type ModalState =
  | { type: 'assign'; einheit: Einheit }
  | { type: 'hausgeld'; einheit: Einheit; ev: EigentumsVerhaeltnis }
  | null

// ────────────────────────────────────────────────────────────────────────────
// Sort / Filter für die Einheiten-Tabelle
// ────────────────────────────────────────────────────────────────────────────
type VmSortKey = 'flaechennummer' | 'typ_code' | 'einheit_nr' | 'lage' | 'eigentuemer' | 'hausgeld_num'
type VmSortDir = 'asc' | 'desc'
interface VmFilters { flaechennummer: string; typ_code: string; einheit_nr: string; lage: string; eigentuemer: string; hausgeld: string }
const VM_EMPTY: VmFilters = { flaechennummer: '', typ_code: '', einheit_nr: '', lage: '', eigentuemer: '', hausgeld: '' }

function VmSortIcon({ active, dir }: { active: boolean; dir: VmSortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

// ────────────────────────────────────────────────────────────────────────────
// Haupt-Seite
// ────────────────────────────────────────────────────────────────────────────
export function VertragsmanagementPage() {
  const qc = useQueryClient()
  const { selectedId: selectedObjektId, selectedName } = useObjektStore()
  const [modal, setModal] = useState<ModalState>(null)
  const [importStatus, setImportStatus] = useState<{ importiert: number; personenkonten_angelegt: number; fehler: string[] } | null>(null)
  const [vorschau, setVorschau] = useState<VertraegeVorschauResponse | null>(null)
  const [vorschauFile, setVorschauFile] = useState<File | null>(null)
  const [loadingVorschau, setLoadingVorschau] = useState(false)
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const evByEinheit = useMemo(
    () => new Map<string, EigentumsVerhaeltnis>(evs.map(ev => [ev.einheit, ev])),
    [evs],
  )

  const [vmSortKey, setVmSortKey] = useState<VmSortKey>('flaechennummer')
  const [vmSortDir, setVmSortDir] = useState<VmSortDir>('asc')
  const [vmFilters, setVmFilters] = useState<VmFilters>(VM_EMPTY)

  const vmRows = useMemo(
    () => einheiten.map(e => {
      const ev = evByEinheit.get(e.id)
      return {
        ...e,
        typ_code: TYP_CODE[e.einheit_typ] ?? e.einheit_typ,
        eigentuemer: ev?.person_name ?? '',
        hausgeld_num: ev?.hausgeld_soll != null ? parseFloat(ev.hausgeld_soll) : null,
        ev,
      }
    }),
    [einheiten, evByEinheit],
  )

  const vmFiltered = useMemo(() => vmRows.filter(r =>
    (r.flaechennummer ?? '').toLowerCase().includes(vmFilters.flaechennummer.toLowerCase()) &&
    r.typ_code.toLowerCase().includes(vmFilters.typ_code.toLowerCase()) &&
    r.einheit_nr.toLowerCase().includes(vmFilters.einheit_nr.toLowerCase()) &&
    r.lage.toLowerCase().includes(vmFilters.lage.toLowerCase()) &&
    r.eigentuemer.toLowerCase().includes(vmFilters.eigentuemer.toLowerCase()) &&
    (vmFilters.hausgeld === '' || (r.hausgeld_num != null && r.hausgeld_num.toFixed(2).includes(vmFilters.hausgeld))),
  ), [vmRows, vmFilters])

  const vmSorted = useMemo(() => [...vmFiltered].sort((a, b) => {
    if (vmSortKey === 'hausgeld_num') {
      const diff = (a.hausgeld_num ?? -1) - (b.hausgeld_num ?? -1)
      return vmSortDir === 'asc' ? diff : -diff
    }
    const getStr = (r: typeof a) => {
      if (vmSortKey === 'flaechennummer') return r.flaechennummer ?? ''
      if (vmSortKey === 'typ_code') return r.typ_code
      if (vmSortKey === 'einheit_nr') return r.einheit_nr
      if (vmSortKey === 'lage') return r.lage
      return r.eigentuemer
    }
    const cmp = getStr(a).toLowerCase().localeCompare(getStr(b).toLowerCase(), 'de', { numeric: true })
    return vmSortDir === 'asc' ? cmp : -cmp
  }), [vmFiltered, vmSortKey, vmSortDir])

  const handleVmSort = (key: VmSortKey) => {
    if (vmSortKey === key) setVmSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setVmSortKey(key); setVmSortDir('asc') }
  }

  const setVmFilter = (key: keyof VmFilters, val: string) =>
    setVmFilters(prev => ({ ...prev, [key]: val }))

  const hasVmFilters = Object.values(vmFilters).some(v => v !== '')

  const vmFi = (key: keyof VmFilters) => (
    <input
      type="text"
      value={vmFilters[key]}
      onChange={e => setVmFilter(key, e.target.value)}
      placeholder="Filter…"
      className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-400"
    />
  )

  const vmThClass = 'text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap cursor-pointer select-none hover:bg-gray-100'

  const refetch = () => {
    qc.invalidateQueries({ queryKey: ['eigentumsverhaeltnisse', 'objekt', selectedObjektId] })
  }

  const handleVorlageDownload = async () => {
    if (!selectedObjektId) return
    const { blob, filename } = await personenApi.vertraegeVorlage(selectedObjektId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedObjektId) return
    setLoadingVorschau(true)
    setImportStatus(null)
    try {
      const result = await personenApi.vertraegeVorschau(selectedObjektId, file)
      setVorschau(result)
      setVorschauFile(file)
    } catch {
      setImportStatus({ importiert: 0, personenkonten_angelegt: 0, fehler: ['Datei konnte nicht gelesen werden.'] })
    } finally {
      setLoadingVorschau(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleImportBestaetigen = async () => {
    if (!vorschauFile || !selectedObjektId) return
    setImporting(true)
    try {
      const result = await personenApi.vertraegeImport(selectedObjektId, vorschauFile)
      setImportStatus(result)
      setVorschau(null)
      setVorschauFile(null)
      refetch()
    } catch {
      setImportStatus({ importiert: 0, personenkonten_angelegt: 0, fehler: ['Import fehlgeschlagen.'] })
      setVorschau(null)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Vertragsmanagement</h1>
        {selectedObjektId && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleVorlageDownload}
              className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 whitespace-nowrap"
            >
              CSV-Vorlage
            </button>
            <label className={`text-sm px-3 py-1.5 rounded border border-blue-300 text-blue-700 hover:bg-blue-50 whitespace-nowrap cursor-pointer ${loadingVorschau ? 'opacity-50 pointer-events-none' : ''}`}>
              {loadingVorschau ? 'Prüfe…' : 'CSV importieren'}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleImportFile}
              />
            </label>
          </div>
        )}
      </div>

      {!selectedObjektId ? (
        <p className="text-sm text-gray-500">Bitte wähle zuerst ein Objekt in der Seitenleiste aus.</p>
      ) : (
        <p className="text-sm text-gray-500">Objekt: <span className="font-medium text-gray-700">{selectedName}</span></p>
      )}

      {importStatus && (
        <div className={`rounded-lg border px-4 py-3 text-sm ${importStatus.fehler.length > 0 ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'}`}>
          <p className="font-medium text-gray-800">
            {importStatus.importiert} Vertrag/Verträge importiert
            {importStatus.personenkonten_angelegt > 0 && ` · ${importStatus.personenkonten_angelegt} Personenkonto/Personenkonten angelegt`}.
          </p>
          {importStatus.fehler.length > 0 && (
            <ul className="mt-1 list-disc list-inside text-amber-800 space-y-0.5">
              {importStatus.fehler.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          )}
          <button type="button" onClick={() => setImportStatus(null)} className="mt-2 text-xs text-gray-400 hover:text-gray-600">Schließen</button>
        </div>
      )}

      {selectedObjektId && (
        loadingE || loadingEV ? (
          <p className="text-sm text-gray-400">Laden…</p>
        ) : einheiten.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Einheiten gefunden.</p>
        ) : (
          <div className="space-y-2">
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className={vmThClass} onClick={() => handleVmSort('flaechennummer')}>
                      Fl.Nr. <VmSortIcon active={vmSortKey === 'flaechennummer'} dir={vmSortDir} />
                    </th>
                    <th className={vmThClass} onClick={() => handleVmSort('typ_code')}>
                      Typ <VmSortIcon active={vmSortKey === 'typ_code'} dir={vmSortDir} />
                    </th>
                    <th className={vmThClass} onClick={() => handleVmSort('einheit_nr')}>
                      Einheit <VmSortIcon active={vmSortKey === 'einheit_nr'} dir={vmSortDir} />
                    </th>
                    <th className={vmThClass} onClick={() => handleVmSort('lage')}>
                      Lage <VmSortIcon active={vmSortKey === 'lage'} dir={vmSortDir} />
                    </th>
                    <th className={vmThClass} onClick={() => handleVmSort('eigentuemer')}>
                      Eigentümer <VmSortIcon active={vmSortKey === 'eigentuemer'} dir={vmSortDir} />
                    </th>
                    <th className={vmThClass} onClick={() => handleVmSort('hausgeld_num')}>
                      Hausgeld-Soll <VmSortIcon active={vmSortKey === 'hausgeld_num'} dir={vmSortDir} />
                    </th>
                    <th className="px-3 py-2 w-32" />
                  </tr>
                  <tr className="bg-white border-b border-gray-100">
                    <td className="px-3 py-1">{vmFi('flaechennummer')}</td>
                    <td className="px-3 py-1">{vmFi('typ_code')}</td>
                    <td className="px-3 py-1">{vmFi('einheit_nr')}</td>
                    <td className="px-3 py-1">{vmFi('lage')}</td>
                    <td className="px-3 py-1">{vmFi('eigentuemer')}</td>
                    <td className="px-3 py-1">{vmFi('hausgeld')}</td>
                    <td />
                  </tr>
                </thead>
                <tbody>
                  {vmSorted.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-6 text-center text-sm text-gray-400">
                        Keine Einheiten entsprechen den Filterkriterien.
                      </td>
                    </tr>
                  ) : (
                    vmSorted.map(r => (
                      <tr key={r.id} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-500 text-xs">{r.flaechennummer || '–'}</td>
                        <td className="px-3 py-2 text-gray-600 font-mono text-xs">{r.typ_code}</td>
                        <td className="px-3 py-2 font-medium text-gray-800">{r.einheit_nr}</td>
                        <td className="px-3 py-2 text-gray-600">{r.lage}</td>
                        <td className="px-3 py-2 text-gray-800">
                          {r.ev ? (
                            <span>
                              {r.ev.person_name}
                              <span className="ml-2 text-xs text-gray-400">seit {r.ev.beginn}</span>
                            </span>
                          ) : (
                            <span className="text-gray-400 italic text-xs">nicht zugewiesen</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-700">
                          {r.hausgeld_num != null
                            ? `${r.hausgeld_num.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €`
                            : '–'}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex gap-1 justify-end">
                            <button
                              type="button"
                              onClick={() => setModal({ type: 'assign', einheit: r })}
                              className="text-xs px-2 py-1 rounded border border-blue-200 text-blue-600 hover:bg-blue-50 whitespace-nowrap"
                            >
                              Eigentümer
                            </button>
                            {r.ev && (
                              <button
                                type="button"
                                onClick={() => setModal({ type: 'hausgeld', einheit: r, ev: r.ev! })}
                                className="text-xs px-2 py-1 rounded border border-green-200 text-green-600 hover:bg-green-50 whitespace-nowrap"
                              >
                                Hausgeld
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between px-1">
              <p className="text-xs text-gray-500">
                {hasVmFilters
                  ? <><strong>{vmSorted.length}</strong> von <strong>{einheiten.length}</strong> Einheiten angezeigt</>
                  : <><strong>{einheiten.length}</strong> Einheit{einheiten.length !== 1 ? 'en' : ''} gesamt</>
                }
              </p>
              {hasVmFilters && (
                <button type="button" onClick={() => setVmFilters(VM_EMPTY)} className="text-xs text-primary-600 hover:text-primary-700 underline">
                  Filter zurücksetzen
                </button>
              )}
            </div>
          </div>
        )
      )}

      {/* Vorschau-Modal */}
      {vorschau && (
        <VertraegeVorschauModal
          vorschau={vorschau}
          importing={importing}
          onImport={handleImportBestaetigen}
          onClose={() => { setVorschau(null); setVorschauFile(null) }}
        />
      )}

      {/* Modals */}
      {modal?.type === 'assign' && (
        <EigentumsZuweisungModal
          einheit={modal.einheit}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refetch() }}
        />
      )}
      {modal?.type === 'hausgeld' && (
        <HausgeldModal
          einheit={modal.einheit}
          ev={modal.ev}
          objektId={modal.einheit.objekt}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); refetch() }}
        />
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Modal: Verträge Vorschau
// ────────────────────────────────────────────────────────────────────────────
const STATUS_STYLE: Record<string, string> = {
  ok: 'bg-green-50 text-green-700 border-green-200',
  warnung: 'bg-amber-50 text-amber-700 border-amber-200',
  fehler: 'bg-red-50 text-red-700 border-red-200',
}
const STATUS_LABEL: Record<string, string> = {
  ok: 'OK',
  warnung: 'Warnung',
  fehler: 'Fehler',
}

function VertraegeVorschauModal({
  vorschau,
  importing,
  onImport,
  onClose,
}: {
  vorschau: VertraegeVorschauResponse
  importing: boolean
  onImport: () => void
  onClose: () => void
}) {
  const importierbar = vorschau.rows.filter(r => r.status !== 'fehler' && r.person_info)
  const fehlerZeilen = vorschau.rows.filter(r => r.status === 'fehler')
  const warnZeilen = vorschau.rows.filter(r => r.status === 'warnung')

  return (
    <Overlay onClose={onClose} wide>
      <h2 className="text-lg font-semibold text-gray-800 mb-1">Verträge-Import — Vorschau</h2>
      <p className="text-sm text-gray-500 mb-4">
        {vorschau.rows.length} Zeilen gelesen ·{' '}
        <span className="text-green-700 font-medium">{importierbar.length} importierbar</span>
        {warnZeilen.length > 0 && <span className="text-amber-700"> · {warnZeilen.length} mit Warnung</span>}
        {fehlerZeilen.length > 0 && <span className="text-red-700"> · {fehlerZeilen.length} mit Fehler (werden übersprungen)</span>}
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4 max-h-[55vh] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200 sticky top-0">
            <tr>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-8">Z.</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-14">Fl.Nr.</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-24">Einheit</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600">Person</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-24">ET ab</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-16">Sollarten</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600 w-20">Status</th>
              <th className="text-left px-2 py-2 font-medium text-gray-600">Hinweise</th>
            </tr>
          </thead>
          <tbody>
            {vorschau.rows.map(zeile => (
              <tr key={zeile.zeile} className="border-t border-gray-100 align-top">
                <td className="px-2 py-1.5 text-gray-400">{zeile.zeile}</td>
                <td className="px-2 py-1.5 font-mono text-gray-700">{zeile.fl_nr}</td>
                <td className="px-2 py-1.5 text-gray-700">
                  {zeile.einheit_info
                    ? <span>{zeile.einheit_info.einheit_nr}<span className="text-gray-400 ml-1">{zeile.einheit_info.lage}</span></span>
                    : <span className="text-red-500">–</span>}
                </td>
                <td className="px-2 py-1.5 text-gray-700">
                  {zeile.person_info
                    ? <span>{zeile.person_info.name}<span className="text-gray-400 ml-1">({zeile.personnummer})</span></span>
                    : zeile.personnummer
                      ? <span className="text-red-500">{zeile.personnummer} nicht gefunden</span>
                      : <span className="text-gray-400 italic">–</span>}
                </td>
                <td className="px-2 py-1.5 text-gray-600">{zeile.et_ab || '–'}</td>
                <td className="px-2 py-1.5 text-gray-600 text-center">{zeile.sollarten.length || '–'}</td>
                <td className="px-2 py-1.5">
                  <span className={`inline-block px-1.5 py-0.5 rounded border text-xs font-medium ${STATUS_STYLE[zeile.status]}`}>
                    {STATUS_LABEL[zeile.status]}
                  </span>
                </td>
                <td className="px-2 py-1.5">
                  {zeile.fehler.length > 0 && (
                    <ul className="text-red-600 space-y-0.5">
                      {zeile.fehler.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  )}
                  {zeile.info.length > 0 && (
                    <ul className="text-amber-700 space-y-0.5">
                      {zeile.info.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
          Abbrechen
        </button>
        <Button
          type="button"
          onClick={onImport}
          disabled={importing || importierbar.length === 0}
        >
          {importing ? 'Importiere…' : `${importierbar.length} Zeile${importierbar.length !== 1 ? 'n' : ''} importieren`}
        </Button>
      </div>
    </Overlay>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Modal: Eigentümer zuweisen
// ────────────────────────────────────────────────────────────────────────────
function EigentumsZuweisungModal({
  einheit,
  onClose,
  onSaved,
}: {
  einheit: Einheit
  onClose: () => void
  onSaved: () => void
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<PersonList[]>([])
  const [selectedPerson, setSelectedPerson] = useState<PersonList | null>(null)
  const [beginn, setBeginn] = useState(new Date().toISOString().split('T')[0])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    const res = await personenApi.list({ search: searchQuery })
    setSearchResults(res)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPerson) { setError('Bitte eine Person auswählen.'); return }
    if (!beginn) { setError('Beginn-Datum ist erforderlich.'); return }
    setIsLoading(true)
    setError('')
    try {
      await personenApi.createEigentumsverhaeltnis({
        einheit: einheit.id,
        person: selectedPerson.id,
        beginn,
      })
      onSaved()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg ?? 'Fehler beim Speichern.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Overlay onClose={onClose}>
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Eigentümer zuweisen — <span className="text-primary-700">{einheit.einheit_nr}</span>
        <span className="ml-2 text-sm font-normal text-gray-500">{einheit.lage}</span>
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Person-Suche */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-700">Person suchen</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleSearch())}
              placeholder="Name, E-Mail oder Personennummer…"
              className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />
            <button
              type="button"
              onClick={handleSearch}
              className="px-3 py-2 rounded bg-gray-100 hover:bg-gray-200 text-sm text-gray-700"
            >
              Suchen
            </button>
          </div>

          {searchResults.length > 0 && !selectedPerson && (
            <div className="rounded border border-gray-200 divide-y divide-gray-100 max-h-48 overflow-y-auto">
              {searchResults.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { setSelectedPerson(p); setSearchResults([]) }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-primary-50 transition-colors"
                >
                  <span className="font-medium text-gray-800">{p.name}</span>
                  {p.email && <span className="ml-2 text-gray-400 text-xs">{p.email}</span>}
                </button>
              ))}
            </div>
          )}

          {selectedPerson && (
            <div className="flex items-center justify-between bg-primary-50 rounded px-3 py-2">
              <span className="text-sm font-medium text-primary-800">{selectedPerson.name}</span>
              <button
                type="button"
                onClick={() => setSelectedPerson(null)}
                className="text-xs text-gray-400 hover:text-red-500"
              >
                ✕
              </button>
            </div>
          )}
        </div>

        {/* Beginn-Datum */}
        <Input
          label="Beginn *"
          type="date"
          value={beginn}
          onChange={e => setBeginn(e.target.value)}
          required
        />

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
            Abbrechen
          </button>
          <Button type="submit" disabled={isLoading || !selectedPerson}>
            {isLoading ? 'Speichern…' : 'Zuweisen'}
          </Button>
        </div>
      </form>
    </Overlay>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Modal: Hausgeld erfassen (Tabelle je Abrechnungsart)
// ────────────────────────────────────────────────────────────────────────────
type HausgeldZeile = { kontoart: string; betrag: string; gueltigAb: string }

function latestHistorie(ev: EigentumsVerhaeltnis, kontoart: string) {
  return ev.hausgeld_historie
    .filter(h => h.kontoart === kontoart)
    .sort((a, b) => b.gueltig_ab.localeCompare(a.gueltig_ab))[0] ?? null
}

function initZeilen(arts: Abrechnungsart[], ev: EigentumsVerhaeltnis): HausgeldZeile[] {
  const today = new Date().toISOString().split('T')[0]
  return arts.map(a => {
    const prev = latestHistorie(ev, `.${a.code}`)
    return {
      kontoart: `.${a.code}`,
      betrag: prev ? parseFloat(prev.betrag).toFixed(2).replace('.', ',') : '',
      gueltigAb: prev?.gueltig_ab ?? today,
    }
  })
}

function HausgeldModal({
  einheit,
  ev,
  objektId,
  onClose,
  onSaved,
}: {
  einheit: Einheit
  ev: EigentumsVerhaeltnis
  objektId: string
  onClose: () => void
  onSaved: () => void
}) {
  const { data: alleArts = [], isLoading: loadingArts } = useQuery({
    queryKey: ['abrechnungsarten', objektId],
    queryFn: () => buchhaltungApi.abrechnungsarten(objektId),
  })

  // Nur Hausgeld-relevante Abrechnungsarten: 900 und 91x (Rücklagen)
  const arts = useMemo(
    () => alleArts.filter(a => a.aktiv && (a.code === '900' || a.code.startsWith('91'))),
    [alleArts],
  )

  const [zeilen, setZeilen] = useState<HausgeldZeile[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (arts.length > 0) setZeilen(initZeilen(arts, ev))
  }, [arts]) // ev ist stabil für dieses Modal

  const updateZeile = (idx: number, field: 'betrag' | 'gueltigAb', value: string) => {
    setZeilen(prev => prev.map((z, i) => i === idx ? { ...z, [field]: value } : z))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const zuSpeichern = zeilen.filter(z => z.betrag.trim() !== '')
    if (zuSpeichern.length === 0) { setError('Bitte mindestens einen Betrag eingeben.'); return }

    const ungueltig = zuSpeichern.filter(z => isNaN(parseFloat(z.betrag.replace(',', '.'))))
    if (ungueltig.length > 0) { setError('Ungültiger Betrag in einer Zeile.'); return }

    const ohneDatum = zuSpeichern.filter(z => !z.gueltigAb)
    if (ohneDatum.length > 0) { setError('Bitte für alle ausgefüllten Zeilen ein Datum angeben.'); return }

    setIsLoading(true)
    setError('')
    try {
      await Promise.all(
        zuSpeichern.map(z =>
          personenApi.createHausgeldHistorie({
            eigentumsverhaeltnis: ev.id,
            betrag: parseFloat(z.betrag.replace(',', '.')).toFixed(2),
            gueltig_ab: z.gueltigAb,
            kontoart: z.kontoart,
          }),
        ),
      )
      onSaved()
    } catch {
      setError('Fehler beim Speichern.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Overlay onClose={onClose} wide>
      <h2 className="text-lg font-semibold text-gray-800 mb-1">
        Hausgeld erfassen — <span className="text-primary-700">{einheit.einheit_nr}</span>
      </h2>
      <p className="text-sm text-gray-500 mb-4">{ev.person_name}</p>

      {loadingArts ? (
        <p className="text-sm text-gray-400 py-4">Abrechnungsarten laden…</p>
      ) : arts.length === 0 ? (
        <p className="text-sm text-amber-600 py-4">
          Keine Abrechnungsarten (900 / 91x) für dieses Objekt gefunden.
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-16">Code</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Bezeichnung</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-32">Betrag (€)</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-36">Gültig ab</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-500 w-28">Zuletzt</th>
                </tr>
              </thead>
              <tbody>
                {arts.map((art, idx) => {
                  const zeile = zeilen[idx]
                  const prev = latestHistorie(ev, `.${art.code}`)
                  if (!zeile) return null
                  return (
                    <tr key={art.id} className="border-t border-gray-100">
                      <td className="px-3 py-2 font-mono text-gray-700 text-xs">.{art.code}</td>
                      <td className="px-3 py-2 text-gray-700">{art.bezeichnung}</td>
                      <td className="px-3 py-2">
                        <div className="relative">
                          <input
                            type="text"
                            inputMode="decimal"
                            value={zeile.betrag}
                            onChange={e => updateZeile(idx, 'betrag', e.target.value)}
                            placeholder="0,00"
                            className="w-full rounded border border-gray-300 px-2 py-1 pr-6 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                          />
                          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">€</span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="date"
                          value={zeile.gueltigAb}
                          onChange={e => updateZeile(idx, 'gueltigAb', e.target.value)}
                          className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                        />
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {prev
                          ? `${parseFloat(prev.betrag).toLocaleString('de-DE', { minimumFractionDigits: 2 })} € (${prev.gueltig_ab})`
                          : '–'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2">
              Abbrechen
            </button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? 'Speichern…' : 'Speichern'}
            </Button>
          </div>
        </form>
      )}
    </Overlay>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Overlay-Wrapper
// ────────────────────────────────────────────────────────────────────────────
function Overlay({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className={`bg-white rounded-xl shadow-xl w-full mx-4 p-6 relative ${wide ? 'max-w-2xl' : 'max-w-md'}`}>
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 text-xl leading-none"
        >
          ×
        </button>
        {children}
      </div>
    </div>
  )
}
