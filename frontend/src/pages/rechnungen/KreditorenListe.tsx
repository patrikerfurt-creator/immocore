import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import { Button } from '../../components/ui/Button'
import { IbanInput } from '../../components/ui/IbanInput'
import type { Kreditor } from '../../types'

// ---------------------------------------------------------------------------
// Typen
// ---------------------------------------------------------------------------
interface KreditorKontoPosition {
  id: string
  herkunft: 'rechnung' | 'wkz'
  rechnungsnummer: string
  rechnungsdatum: string | null
  faelligkeitsdatum: string | null
  betrag_brutto: number | null
  betrag_offen: number | null
  status: string
  objekt: string | null
  sachkonto_nr: string | null
  sachkonto_name: string | null
  opos_nr: string | null
  buchungsdatum: string | null
  buchung_status: string | null
}

const STATUS_LABEL: Record<string, string> = {
  importiert: 'Importiert',
  erfasst: 'Erfasst',
  freigegeben: 'Freigegeben',
  gebucht: 'Gebucht',
  bezahlt: 'Bezahlt',
  abgelehnt: 'Abgelehnt',
  prueffall: 'Prüffall',
  duplikat: 'Duplikat',
  in_pruefung: 'In Prüfung',
  fehler: 'Fehler',
  // WKZ-OP Status
  offen: 'Offen',
  teilbezahlt: 'Teilbezahlt',
  storniert: 'Storniert',
  erzeugt: 'Erzeugt',
  bescheid_fehlt: 'Bescheid fehlt',
  bankabgang_erfolgt: 'Bezahlt',
  abweichend_geklaert: 'Abweichend',
  verworfen: 'Verworfen',
}

const STATUS_COLOR: Record<string, string> = {
  gebucht: 'bg-blue-100 text-blue-700',
  bezahlt: 'bg-green-100 text-green-700',
  bankabgang_erfolgt: 'bg-green-100 text-green-700',
  freigegeben: 'bg-yellow-100 text-yellow-700',
  abgelehnt: 'bg-red-100 text-red-700',
  importiert: 'bg-gray-100 text-gray-600',
  erfasst: 'bg-gray-100 text-gray-600',
  prueffall: 'bg-orange-100 text-orange-700',
  offen: 'bg-orange-100 text-orange-700',
  erzeugt: 'bg-orange-100 text-orange-700',
  bescheid_fehlt: 'bg-red-100 text-red-700',
  teilbezahlt: 'bg-yellow-100 text-yellow-700',
  storniert: 'bg-gray-100 text-gray-400',
  verworfen: 'bg-gray-100 text-gray-400',
}

function fmt(date: string | null) {
  if (!date) return '—'
  return new Date(date).toLocaleDateString('de-DE')
}

function fmtEur(val: number | null) {
  if (val == null) return '—'
  return val.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
}

// ---------------------------------------------------------------------------
// Kreditorenkonto-Modal
// ---------------------------------------------------------------------------
function KreditorKontoModal({
  kreditor,
  onClose,
}: {
  kreditor: Kreditor
  onClose: () => void
}) {
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 6 }, (_, i) => currentYear - i)
  const [selectedJahr, setSelectedJahr] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['kreditor-kontoauszug', kreditor.id, selectedJahr],
    queryFn: () => rechnungenApi.kreditorKontoauszug(kreditor.id, selectedJahr ? { jahr: selectedJahr } : {}),
  })

  const positionen: KreditorKontoPosition[] = data?.positionen ?? []
  const gesamtOffen = positionen
    .filter(p => p.status !== 'bezahlt' && p.status !== 'storniert' && p.betrag_offen != null)
    .reduce((s, p) => s + (p.betrag_offen ?? 0), 0)

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 overflow-y-auto py-10">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-5xl mx-4">
        {/* Header */}
        <div className="flex justify-between items-start p-6 border-b">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Kreditorenkonto</h2>
            <p className="text-gray-500 text-sm mt-0.5">{kreditor.name}</p>
            {kreditor.iban && (
              <p className="text-xs text-gray-400 font-mono mt-0.5">
                {kreditor.iban}{kreditor.bic ? ` · ${kreditor.bic}` : ''}
              </p>
            )}
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">Jahr:</span>
              <select
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary-400"
                value={selectedJahr}
                onChange={e => setSelectedJahr(e.target.value)}
              >
                <option value="">Alle</option>
                {years.map(y => (
                  <option key={y} value={String(y)}>{y}</option>
                ))}
              </select>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
          </div>
        </div>

        {/* Saldo-Info */}
        <div className="px-6 py-3 bg-gray-50 border-b flex gap-8 text-sm">
          <div>
            <span className="text-gray-500">Rechnungen gesamt</span>
            <span className="ml-2 font-semibold text-gray-800">{positionen.length}</span>
          </div>
          <div>
            <span className="text-gray-500">Offene Verbindlichkeiten</span>
            <span className="ml-2 font-semibold text-orange-700">{fmtEur(gesamtOffen)}</span>
          </div>
        </div>

        {/* Tabelle */}
        <div className="p-6">
          {isLoading ? (
            <div className="text-gray-400 text-sm text-center py-10">Lade Kontoauszug…</div>
          ) : positionen.length === 0 ? (
            <div className="text-gray-400 text-sm text-center py-10">
              Keine Rechnungen für diesen Kreditor vorhanden.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">OPOS-Nr.</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Bezeichnung / Rech.-Nr.</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Datum</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Fälligkeit</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Objekt</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Sachkonto</th>
                  <th className="text-right px-3 py-2 text-gray-500 font-medium">Betrag</th>
                  <th className="text-right px-3 py-2 text-gray-500 font-medium">Offen</th>
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {positionen.map(p => (
                  <tr key={p.id} className={`border-t hover:bg-gray-50 ${p.herkunft === 'wkz' ? 'bg-blue-50/30' : ''}`}>
                    <td className="px-3 py-2 font-mono text-xs text-blue-700 font-semibold">
                      {p.opos_nr ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-gray-700">
                      <div className="flex items-center gap-1.5">
                        {p.herkunft === 'wkz' && (
                          <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium shrink-0">WKZ</span>
                        )}
                        <span className="truncate max-w-xs" title={p.rechnungsnummer}>{p.rechnungsnummer || '—'}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-gray-600">{fmt(p.rechnungsdatum)}</td>
                    <td className="px-3 py-2 text-gray-600">{fmt(p.faelligkeitsdatum)}</td>
                    <td className="px-3 py-2 text-gray-600">{p.objekt ?? '—'}</td>
                    <td className="px-3 py-2 text-gray-600 text-xs">
                      {p.sachkonto_nr ? `${p.sachkonto_nr} ${p.sachkonto_name ?? ''}` : '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-medium text-gray-800">
                      {fmtEur(p.betrag_brutto)}
                    </td>
                    <td className="px-3 py-2 text-right font-medium">
                      {p.betrag_offen != null && p.betrag_offen > 0
                        ? <span className="text-orange-700">{fmtEur(p.betrag_offen)}</span>
                        : p.betrag_offen === 0
                          ? <span className="text-green-700">{fmtEur(0)}</span>
                          : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLOR[p.status] ?? 'bg-gray-100 text-gray-600'}`}>
                        {STATUS_LABEL[p.status] ?? p.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Formular (Anlegen / Bearbeiten)
// ---------------------------------------------------------------------------
function KreditorForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<Kreditor>
  onSave: (data: Partial<Kreditor>) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<Partial<Kreditor>>(initial ?? {})
  const set = (field: keyof Kreditor) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(prev => ({ ...prev, [field]: e.target.value }))

  return (
    <div className="bg-white rounded-xl border shadow-sm p-6 mb-6">
      <h2 className="font-bold text-gray-800 mb-4">
        {initial?.id ? 'Kreditor bearbeiten' : 'Neuer Kreditor'}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Name *</label>
          <input type="text" value={form.name ?? ''} onChange={set('name')}
                 className="border rounded-lg px-3 py-2 text-sm w-full" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">IBAN</label>
          <IbanInput
            value={form.iban ?? ''}
            onChange={v => setForm(f => ({ ...f, iban: v }))}
            onBicFound={(bic) => setForm(f => ({ ...f, bic: f.bic || bic }))}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">BIC</label>
          <input type="text" value={form.bic ?? ''} onChange={set('bic')}
                 placeholder="wird automatisch befüllt"
                 className="border rounded-lg px-3 py-2 text-sm w-full font-mono" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">E-Mail</label>
          <input type="email" value={form.email ?? ''} onChange={set('email')}
                 className="border rounded-lg px-3 py-2 text-sm w-full" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Straße</label>
          <input type="text" value={form.strasse ?? ''} onChange={set('strasse')}
                 className="border rounded-lg px-3 py-2 text-sm w-full" />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">PLZ</label>
            <input type="text" value={form.plz ?? ''} onChange={set('plz')}
                   className="border rounded-lg px-3 py-2 text-sm w-full" />
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Ort</label>
            <input type="text" value={form.ort ?? ''} onChange={set('ort')}
                   className="border rounded-lg px-3 py-2 text-sm w-full" />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Telefon</label>
          <input type="text" value={form.telefon ?? ''} onChange={set('telefon')}
                 className="border rounded-lg px-3 py-2 text-sm w-full" />
        </div>
      </div>
      <div className="flex gap-3 justify-end mt-4">
        <Button variant="secondary" onClick={onCancel}>Abbrechen</Button>
        <Button onClick={() => onSave(form)} disabled={!form.name}>Speichern</Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptseite
// ---------------------------------------------------------------------------
type KredSortKey = 'name' | 'kreditorennummer' | 'iban' | 'ort' | 'email' | 'rechnungen_anzahl'
type KredSortDir = 'asc' | 'desc'
interface KredFilters { name: string; kreditorennummer: string; iban: string; ort: string; email: string; rechnungen: string }
const KRED_EMPTY: KredFilters = { name: '', kreditorennummer: '', iban: '', ort: '', email: '', rechnungen: '' }
type KredRow = Kreditor & { ort_str: string }

function KredSortIcon({ active, dir }: { active: boolean; dir: KredSortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

export function KreditorenListe() {
  const qc = useQueryClient()
  const [editKreditor, setEditKreditor] = useState<Kreditor | null | 'neu'>(null)
  const [kontoKreditor, setKontoKreditor] = useState<Kreditor | null>(null)
  const [sortKey, setSortKey] = useState<KredSortKey>('name')
  const [sortDir, setSortDir] = useState<KredSortDir>('asc')
  const [filters, setFilters] = useState<KredFilters>(KRED_EMPTY)

  const { data: kreditoren, isLoading } = useQuery({
    queryKey: ['kreditoren'],
    queryFn: () => rechnungenApi.kreditoren(),
  })

  const saveMut = useMutation({
    mutationFn: (data: Partial<Kreditor>) =>
      editKreditor && editKreditor !== 'neu'
        ? rechnungenApi.updateKreditor(editKreditor.id, data)
        : rechnungenApi.createKreditor(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kreditoren'] })
      setEditKreditor(null)
    },
  })

  const deaktMut = useMutation({
    mutationFn: (id: string) => rechnungenApi.deaktivierenKreditor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kreditoren'] }),
  })

  const rows = useMemo<KredRow[]>(
    () => (kreditoren ?? []).map(k => ({ ...k, ort_str: [k.plz, k.ort].filter(Boolean).join(' ') })),
    [kreditoren],
  )

  const filtered = useMemo(() => rows.filter(r =>
    r.name.toLowerCase().includes(filters.name.toLowerCase()) &&
    (r.kreditorennummer ?? '').includes(filters.kreditorennummer) &&
    (r.iban ?? '').toLowerCase().includes(filters.iban.toLowerCase()) &&
    r.ort_str.toLowerCase().includes(filters.ort.toLowerCase()) &&
    (r.email ?? '').toLowerCase().includes(filters.email.toLowerCase()) &&
    (filters.rechnungen === '' || String(r.rechnungen_anzahl).includes(filters.rechnungen)),
  ), [rows, filters])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    if (sortKey === 'rechnungen_anzahl') {
      const diff = (a.rechnungen_anzahl ?? 0) - (b.rechnungen_anzahl ?? 0)
      return sortDir === 'asc' ? diff : -diff
    }
    const getStr = (r: KredRow) => {
      if (sortKey === 'name') return r.name
      if (sortKey === 'kreditorennummer') return r.kreditorennummer ?? ''
      if (sortKey === 'iban') return r.iban ?? ''
      if (sortKey === 'ort') return r.ort_str
      return r.email ?? ''
    }
    const cmp = getStr(a).toLowerCase().localeCompare(getStr(b).toLowerCase(), 'de', { numeric: true })
    return sortDir === 'asc' ? cmp : -cmp
  }), [filtered, sortKey, sortDir])

  const handleSort = (key: KredSortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const setFilter = (key: keyof KredFilters, value: string) =>
    setFilters(prev => ({ ...prev, [key]: value }))

  const hasFilters = Object.values(filters).some(v => v !== '')

  const thClass = 'text-left px-3 py-2 text-gray-500 font-medium whitespace-nowrap cursor-pointer select-none hover:bg-gray-100'

  const fi = (key: keyof KredFilters) => (
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
        <h1 className="text-2xl font-bold text-gray-900">Kreditoren</h1>
        <Button onClick={() => setEditKreditor('neu')}>+ Neuer Kreditor</Button>
      </div>

      {kontoKreditor && (
        <KreditorKontoModal
          kreditor={kontoKreditor}
          onClose={() => setKontoKreditor(null)}
        />
      )}

      {editKreditor && (
        <KreditorForm
          initial={editKreditor === 'neu' ? {} : editKreditor}
          onSave={data => saveMut.mutate(data)}
          onCancel={() => setEditKreditor(null)}
        />
      )}

      {isLoading ? (
        <div className="text-gray-400 text-sm">Lade Kreditoren…</div>
      ) : (
        <div className="space-y-2">
          <div className="bg-white rounded-xl border shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className={thClass} onClick={() => handleSort('name')}>
                    Name <KredSortIcon active={sortKey === 'name'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('kreditorennummer')}>
                    Kred.-Nr. <KredSortIcon active={sortKey === 'kreditorennummer'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('iban')}>
                    IBAN <KredSortIcon active={sortKey === 'iban'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('ort')}>
                    Ort <KredSortIcon active={sortKey === 'ort'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('email')}>
                    E-Mail <KredSortIcon active={sortKey === 'email'} dir={sortDir} />
                  </th>
                  <th className={`${thClass} text-right`} onClick={() => handleSort('rechnungen_anzahl')}>
                    Rechnungen <KredSortIcon active={sortKey === 'rechnungen_anzahl'} dir={sortDir} />
                  </th>
                  <th className="px-3 py-2 w-28" />
                </tr>
                <tr className="bg-white border-b border-gray-100">
                  <td className="px-3 py-1">{fi('name')}</td>
                  <td className="px-3 py-1">{fi('kreditorennummer')}</td>
                  <td className="px-3 py-1">{fi('iban')}</td>
                  <td className="px-3 py-1">{fi('ort')}</td>
                  <td className="px-3 py-1">{fi('email')}</td>
                  <td className="px-3 py-1">{fi('rechnungen')}</td>
                  <td />
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-gray-400">
                      {hasFilters ? 'Keine Kreditoren entsprechen den Filterkriterien.' : 'Keine Kreditoren vorhanden — werden beim Import automatisch angelegt'}
                    </td>
                  </tr>
                ) : (
                  sorted.map(k => (
                    <tr key={k.id} className="border-t hover:bg-gray-50">
                      <td className="px-3 py-2.5 font-medium text-gray-800">{k.name}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-indigo-700 font-semibold">{k.kreditorennummer || '—'}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-gray-500">{k.iban || '—'}</td>
                      <td className="px-3 py-2.5 text-gray-600">{k.ort_str || '—'}</td>
                      <td className="px-3 py-2.5 text-gray-600">{k.email || '—'}</td>
                      <td className="px-3 py-2.5 text-right">
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          {k.rechnungen_anzahl}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="flex gap-2 justify-end">
                          <button onClick={() => setKontoKreditor(k)} className="text-xs text-indigo-600 hover:underline">Konto</button>
                          <button onClick={() => setEditKreditor(k)} className="text-xs text-blue-600 hover:underline">Bearbeiten</button>
                          <button
                            onClick={() => { if (confirm(`Kreditor "${k.name}" deaktivieren?`)) deaktMut.mutate(k.id) }}
                            className="text-xs text-gray-400 hover:text-red-500"
                          >
                            Deaktivieren
                          </button>
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
              {hasFilters
                ? <><strong>{sorted.length}</strong> von <strong>{rows.length}</strong> Kreditor{rows.length !== 1 ? 'en' : ''} angezeigt</>
                : <><strong>{rows.length}</strong> Kreditor{rows.length !== 1 ? 'en' : ''} gesamt</>
              }
            </p>
            {hasFilters && (
              <button type="button" onClick={() => setFilters(KRED_EMPTY)} className="text-xs text-primary-600 hover:text-primary-700 underline">
                Filter zurücksetzen
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
