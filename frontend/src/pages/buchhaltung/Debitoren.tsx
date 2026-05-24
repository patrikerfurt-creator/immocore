import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import { wirtschaftsjahreApi } from '../../api/wirtschaftsjahre'
import { personenApi } from '../../api/personen'
import { Badge } from '../../components/ui/Badge'
import { IbanInput } from '../../components/ui/IbanInput'
import { useObjektStore } from '../../stores/objekt'
import type {
  PersonenkontoSaldo,
  KontoauszugPosition,
  SEPAMandat,
  Wirtschaftsjahr,
  ZugeordneterOP,
} from '../../types'

const EUR = (v: number | null | undefined) =>
  (v ?? 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')
const MONAT = (s: string) =>
  new Date(s).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })

type View = 'liste' | 'kontoauszug' | 'buchung-detail'

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export function Debitoren() {
  const objektId = useObjektStore(s => s.selectedId)
  const [view, setView]                   = useState<View>('liste')
  const [selectedKonto, setSelectedKonto] = useState<PersonenkontoSaldo | null>(null)
  const [selectedBuchung, setSelectedBuchung] = useState<KontoauszugPosition | null>(null)
  const [selectedWjId, setSelectedWjId]   = useState<string>('')

  if (!objektId) {
    return <div className="p-6 text-gray-500">Bitte zuerst ein Objekt auswählen.</div>
  }

  const openKonto = (k: PersonenkontoSaldo) => {
    setSelectedKonto(k)
    setView('kontoauszug')
  }

  const openBuchung = (b: KontoauszugPosition) => {
    if (!b.hat_detail) return
    setSelectedBuchung(b)
    setView('buchung-detail')
  }

  const backToListe = () => { setSelectedKonto(null); setView('liste') }
  const backToKonto = () => { setSelectedBuchung(null); setView('kontoauszug') }

  return (
    <div>
      {view === 'liste' && (
        <PersonenkontoListe
          objektId={objektId}
          selectedWjId={selectedWjId}
          onWjChange={setSelectedWjId}
          onSelect={openKonto}
        />
      )}
      {view === 'kontoauszug' && selectedKonto && (
        <KontoauszugView
          konto={selectedKonto}
          objektId={objektId}
          wjId={selectedWjId}
          onBack={backToListe}
          onBuchungClick={openBuchung}
        />
      )}
      {view === 'buchung-detail' && selectedKonto && selectedBuchung && (
        <BuchungDetailView
          personenkontoId={selectedKonto.id}
          buchung={selectedBuchung}
          onBack={backToKonto}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ebene 1: Personenkonten-Liste
// ---------------------------------------------------------------------------

type DebSortKey = 'kontonummer' | 'eigentuemer_name' | 'einheit_nr' | 'saldo_offen' | 'status' | 'sepa'
type DebSortDir = 'asc' | 'desc'
interface DebFilters {
  kontonummer: string; eigentuemer_name: string; einheit_nr: string
  saldo: string; status: string; sepa: string
}
const DEB_EMPTY: DebFilters = {
  kontonummer: '', eigentuemer_name: '', einheit_nr: '', saldo: '', status: '', sepa: '',
}

function DebSortIcon({ active, dir }: { active: boolean; dir: DebSortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

function PersonenkontoListe({
  objektId,
  selectedWjId,
  onWjChange,
  onSelect,
}: {
  objektId: string
  selectedWjId: string
  onWjChange: (id: string) => void
  onSelect: (k: PersonenkontoSaldo) => void
}) {
  const [nurOffen, setNurOffen]     = useState(false)
  const [sortKey, setSortKey]       = useState<DebSortKey>('kontonummer')
  const [sortDir, setSortDir]       = useState<DebSortDir>('asc')
  const [filters, setFilters]       = useState<DebFilters>(DEB_EMPTY)

  // Wirtschaftsjahre für dieses Objekt
  const { data: wjListe = [] } = useQuery<Wirtschaftsjahr[]>({
    queryKey: ['wirtschaftsjahre', objektId],
    queryFn: () => wirtschaftsjahreApi.list({ objekt: objektId }),
    enabled: !!objektId,
  })

  // Saldo-Daten: nach WJ gefiltert wenn ausgewählt
  const { data: konten, isLoading } = useQuery({
    queryKey: ['personenkonten-saldo', objektId, selectedWjId],
    queryFn: () => buchhaltungApi.personenkontenMitSaldo(
      objektId,
      selectedWjId ? { wirtschaftsjahr: selectedWjId } : undefined,
    ),
  })

  const gesamtOffen = (konten ?? []).reduce((s, k) => s + k.saldo_offen, 0)

  const filtered = useMemo(() => (konten ?? []).filter(k =>
    (!nurOffen || k.saldo_offen > 0) &&
    k.kontonummer.toLowerCase().includes(filters.kontonummer.toLowerCase()) &&
    k.eigentuemer_name.toLowerCase().includes(filters.eigentuemer_name.toLowerCase()) &&
    (k.einheit_nr ?? '').toLowerCase().includes(filters.einheit_nr.toLowerCase()) &&
    (filters.saldo === '' || EUR(k.saldo_offen).includes(filters.saldo)) &&
    k.status.toLowerCase().includes(filters.status.toLowerCase()) &&
    (filters.sepa === '' || (k.sepa_mandat?.aktiv ? 'ja' : 'nein').includes(filters.sepa.toLowerCase())),
  ), [konten, filters, nurOffen])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    if (sortKey === 'saldo_offen') {
      const diff = a.saldo_offen - b.saldo_offen
      return sortDir === 'asc' ? diff : -diff
    }
    if (sortKey === 'sepa') {
      const av = a.sepa_mandat?.aktiv ? 1 : 0
      const bv = b.sepa_mandat?.aktiv ? 1 : 0
      return sortDir === 'asc' ? av - bv : bv - av
    }
    const getStr = (k: PersonenkontoSaldo) => {
      if (sortKey === 'kontonummer')    return k.kontonummer
      if (sortKey === 'eigentuemer_name') return k.eigentuemer_name
      if (sortKey === 'einheit_nr')     return k.einheit_nr ?? ''
      return k.status
    }
    const cmp = getStr(a).toLowerCase().localeCompare(getStr(b).toLowerCase(), 'de', { numeric: true })
    return sortDir === 'asc' ? cmp : -cmp
  }), [filtered, sortKey, sortDir])

  const handleSort = (key: DebSortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const setFilter = (key: keyof DebFilters, val: string) =>
    setFilters(prev => ({ ...prev, [key]: val }))

  const hasFilters = Object.values(filters).some(v => v !== '') || nurOffen

  const thClass = 'text-left px-3 py-2 text-gray-600 font-medium whitespace-nowrap cursor-pointer select-none hover:bg-gray-100'

  const fi = (key: keyof DebFilters) => (
    <input
      type="text"
      value={filters[key]}
      onChange={e => setFilter(key, e.target.value)}
      placeholder="Filter…"
      className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-400"
    />
  )

  // Ausgewähltes WJ-Label
  const selectedWj = wjListe.find(w => w.id === selectedWjId)
  const anzahlMitSaldo = nurOffen ? filtered.length : (konten ?? []).filter(k => k.saldo_offen > 0).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">Debitoren / Personenkonten</h1>
        <div className="flex items-center gap-2 flex-wrap">

          {/* WJ-Selektor */}
          <select
            value={selectedWjId}
            onChange={e => onWjChange(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">Alle Wirtschaftsjahre</option>
            {[...wjListe].sort((a, b) => b.jahr - a.jahr).map(wj => (
              <option key={wj.id} value={wj.id}>
                WJ {wj.jahr}{wj.status === 'offen' ? ' (offen)' : ' (abgeschl.)'}
              </option>
            ))}
          </select>

          {/* Nur offene Posten */}
          <button
            onClick={() => setNurOffen(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium border transition-colors ${
              nurOffen
                ? 'bg-red-50 border-red-300 text-red-700 hover:bg-red-100'
                : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
            title={nurOffen
              ? 'Alle Personenkonten anzeigen'
              : `Nur ${anzahlMitSaldo} Konten mit offenem Saldo anzeigen`}
          >
            {nurOffen ? '✕ ' : ''}Offene Posten
            {!nurOffen && anzahlMitSaldo > 0 && (
              <span className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-100 text-red-700 text-xs font-bold">
                {anzahlMitSaldo}
              </span>
            )}
          </button>

          {/* Gesamtsaldo */}
          <div className="text-sm text-gray-500">
            Gesamt offen:{' '}
            <span className={`font-semibold ${gesamtOffen > 0 ? 'text-red-600' : 'text-green-600'}`}>
              {EUR(gesamtOffen)}
            </span>
            {selectedWj && (
              <span className="ml-1 text-gray-400 text-xs">({selectedWj.jahr})</span>
            )}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Personenkonten…</div>
      ) : (
        <div className="space-y-2">
          <div className="bg-white rounded-lg border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className={thClass} onClick={() => handleSort('kontonummer')}>
                    Konto-Nr. <DebSortIcon active={sortKey === 'kontonummer'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('eigentuemer_name')}>
                    Eigentümer <DebSortIcon active={sortKey === 'eigentuemer_name'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('einheit_nr')}>
                    Einheit <DebSortIcon active={sortKey === 'einheit_nr'} dir={sortDir} />
                  </th>
                  <th className={`${thClass} text-right`} onClick={() => handleSort('saldo_offen')}>
                    Saldo offen <DebSortIcon active={sortKey === 'saldo_offen'} dir={sortDir} />
                  </th>
                  <th className={thClass} onClick={() => handleSort('status')}>
                    Status <DebSortIcon active={sortKey === 'status'} dir={sortDir} />
                  </th>
                  <th className={`${thClass} text-center`} onClick={() => handleSort('sepa')}>
                    SEPA <DebSortIcon active={sortKey === 'sepa'} dir={sortDir} />
                  </th>
                </tr>
                <tr className="bg-white border-b border-gray-100">
                  <td className="px-3 py-1">{fi('kontonummer')}</td>
                  <td className="px-3 py-1">{fi('eigentuemer_name')}</td>
                  <td className="px-3 py-1">{fi('einheit_nr')}</td>
                  <td className="px-3 py-1">{fi('saldo')}</td>
                  <td className="px-3 py-1">{fi('status')}</td>
                  <td className="px-3 py-1">{fi('sepa')}</td>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-gray-400">
                      {hasFilters
                        ? 'Keine Einträge entsprechen den Filterkriterien.'
                        : 'Keine Personenkonten vorhanden'}
                    </td>
                  </tr>
                ) : sorted.map(k => (
                  <tr
                    key={k.id}
                    className="border-t hover:bg-blue-50 cursor-pointer transition-colors"
                    onClick={() => onSelect(k)}
                  >
                    <td className="px-3 py-2.5 font-mono font-semibold text-blue-700">{k.kontonummer}</td>
                    <td className="px-3 py-2.5 font-medium text-gray-900">{k.eigentuemer_name}</td>
                    <td className="px-3 py-2.5 text-gray-500">{k.einheit_nr || '—'}</td>
                    <td className={`px-3 py-2.5 text-right font-semibold tabular-nums ${k.saldo_offen > 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {EUR(k.saldo_offen)}
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge value={k.status} />
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {k.sepa_mandat?.aktiv
                        ? <span className="text-green-500 text-base">✓</span>
                        : <span className="text-gray-300 text-base">—</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-gray-500">
              {hasFilters
                ? <><strong>{sorted.length}</strong> von <strong>{(konten ?? []).length}</strong> Konto{(konten ?? []).length !== 1 ? 'en' : ''} angezeigt</>
                : <><strong>{(konten ?? []).length}</strong> Personenkonto{(konten ?? []).length !== 1 ? 'en' : ''} gesamt</>
              }
            </p>
            {hasFilters && (
              <button
                type="button"
                onClick={() => { setFilters(DEB_EMPTY); setNurOffen(false) }}
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

// ---------------------------------------------------------------------------
// Ebene 2: Kontoauszug (Gesamt-Buchungen)
// ---------------------------------------------------------------------------

function KontoauszugView({
  konto,
  objektId,
  wjId,
  onBack,
  onBuchungClick,
}: {
  konto: PersonenkontoSaldo
  objektId: string
  wjId: string
  onBack: () => void
  onBuchungClick: (b: KontoauszugPosition) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['kontoauszug', konto.id, wjId],
    queryFn: () => buchhaltungApi.kontoauszug(konto.id, wjId ? { wirtschaftsjahr: wjId } : undefined),
  })

  return (
    <div>
      <button onClick={onBack} className="flex items-center gap-2 text-sm text-blue-600 mb-4 hover:underline">
        ← Zurück zur Übersicht
      </button>

      <div className="bg-white rounded-lg border p-5 mb-4">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Personenkonto</div>
            <h2 className="text-xl font-bold text-gray-900">
              <span className="font-mono text-blue-700 mr-3">{konto.kontonummer}</span>
              {konto.eigentuemer_name}
            </h2>
            {konto.einheit_nr && (
              <div className="text-sm text-gray-500 mt-1">Einheit {konto.einheit_nr}</div>
            )}
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-400 mb-1">
              {wjId ? 'Saldo (WJ-gefiltert)' : 'Aktueller Saldo'}
            </div>
            <div className={`text-2xl font-bold tabular-nums ${
              (data?.saldo_gesamt ?? 0) > 0 ? 'text-red-600' : 'text-green-600'
            }`}>
              {EUR(data?.saldo_gesamt ?? konto.saldo_offen)}
            </div>
          </div>
        </div>
      </div>

      <LastschriftmandatSection konto={konto} objektId={objektId} />

      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Kontoauszug…</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600 font-medium w-40">OPOS-Nr.</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium w-32">Datum</th>
                <th className="text-left px-4 py-3 text-gray-600 font-medium">Text</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Soll</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Haben</th>
                <th className="text-right px-4 py-3 text-gray-600 font-medium w-28">Saldo</th>
                <th className="w-8"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.positionen ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-400">
                    Keine Buchungen vorhanden
                  </td>
                </tr>
              ) : (data?.positionen ?? []).map(pos => (
                <tr
                  key={pos.id}
                  onClick={() => onBuchungClick(pos)}
                  className={`border-t transition-colors ${
                    pos.hat_detail
                      ? 'hover:bg-blue-50 cursor-pointer'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-blue-700">
                    {pos.opos_nr ?? pos.bu_nr ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 whitespace-nowrap">{DATUM(pos.buchungsdatum)}</td>
                  <td className="px-4 py-2.5 text-gray-800 max-w-xs truncate">{pos.buchungstext || '—'}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-gray-800">
                    {pos.soll != null ? EUR(pos.soll) : ''}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-green-700">
                    {pos.haben != null ? EUR(pos.haben) : ''}
                  </td>
                  <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${
                    pos.saldo > 0 ? 'text-red-600' : pos.saldo < 0 ? 'text-green-600' : 'text-gray-500'
                  }`}>
                    {EUR(pos.saldo)}
                  </td>
                  <td className="px-2 py-2.5 text-gray-400 text-xs">
                    {pos.hat_detail ? '›' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
            {(data?.positionen ?? []).length > 0 && (
              <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                <tr>
                  <td colSpan={5} className="px-4 py-3 text-right font-semibold text-gray-700">
                    Gesamtsaldo
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-bold text-base ${
                    (data?.saldo_gesamt ?? 0) > 0 ? 'text-red-600' : 'text-green-600'
                  }`}>
                    {EUR(data?.saldo_gesamt ?? 0)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
          {(data?.positionen ?? []).some(p => p.hat_detail) && (
            <div className="px-4 py-2 text-xs text-gray-400 border-t bg-gray-50">
              Buchungen mit › anklicken für Abrechnungsarten-Detail und zugeordnete Offene Posten
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Lastschriftmandat-Sektion
// ---------------------------------------------------------------------------

const inputCls = 'w-full text-sm border border-gray-300 rounded px-2.5 py-1.5 focus:outline-none focus:border-blue-500'
const labelCls = 'text-xs text-gray-400 mb-1'

function LastschriftmandatSection({ konto, objektId }: { konto: PersonenkontoSaldo; objektId: string }) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [mandat, setMandat]     = useState<SEPAMandat | null>(konto.sepa_mandat)
  const [formData, setFormData] = useState({ mandatsreferenz: '', iban: '', bic: '', unterzeichnet_am: '' })
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const heute = new Date().toISOString().split('T')[0]

  const openCreate = () => {
    setFormData({
      mandatsreferenz: `${konto.kontonummer}-${heute.replace(/-/g, '')}`,
      iban: konto.eigentuemer_ibans[0] ?? '',
      bic: '',
      unterzeichnet_am: heute,
    })
    setError(null)
    setShowForm(true)
  }

  const openEdit = () => {
    if (!mandat) return
    setFormData({
      mandatsreferenz: mandat.mandatsreferenz,
      iban: mandat.iban,
      bic: mandat.bic,
      unterzeichnet_am: mandat.unterzeichnet_am,
    })
    setError(null)
    setShowForm(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      if (mandat) {
        const updated = await personenApi.updateSepaMandat(mandat.id, formData)
        setMandat(updated)
      } else {
        const created = await personenApi.createSepaMandat({ ...formData, aktiv: true })
        await personenApi.linkSepaMandat(konto.eigentuemer_id, created.id)
        setMandat(created)
      }
      setShowForm(false)
      queryClient.invalidateQueries({ queryKey: ['personenkonten-saldo', objektId] })
    } catch {
      setError('Fehler beim Speichern. Bitte Eingaben prüfen.')
    } finally {
      setSaving(false)
    }
  }

  const toggleAktiv = async () => {
    if (!mandat) return
    setSaving(true)
    try {
      const updated = await personenApi.updateSepaMandat(mandat.id, { aktiv: !mandat.aktiv })
      setMandat(updated)
      queryClient.invalidateQueries({ queryKey: ['personenkonten-saldo', objektId] })
    } catch {
      setError('Fehler beim Aktualisieren.')
    } finally {
      setSaving(false)
    }
  }

  const set = (field: keyof typeof formData, value: string) =>
    setFormData(prev => ({ ...prev, [field]: value }))

  return (
    <div className="bg-white rounded-lg border p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Lastschriftmandat</h3>
        {!mandat && !showForm && (
          <button onClick={openCreate} className="text-sm text-blue-600 hover:text-blue-700">
            + Mandat anlegen
          </button>
        )}
        {mandat && !showForm && (
          <div className="flex gap-3">
            <button onClick={openEdit} className="text-xs text-gray-500 hover:text-gray-700">Bearbeiten</button>
            <button
              onClick={toggleAktiv}
              disabled={saving}
              className={`text-xs ${mandat.aktiv ? 'text-red-500 hover:text-red-700' : 'text-green-600 hover:text-green-800'}`}
            >
              {mandat.aktiv ? 'Deaktivieren' : 'Aktivieren'}
            </button>
          </div>
        )}
      </div>

      {!mandat && !showForm && (
        <p className="text-sm text-gray-400">Kein Lastschriftmandat hinterlegt.</p>
      )}

      {mandat && !showForm && (
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <dt className="text-xs text-gray-400">Mandatsreferenz</dt>
            <dd className="font-mono text-gray-800">{mandat.mandatsreferenz}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">IBAN</dt>
            <dd className="font-mono text-gray-800">{mandat.iban}</dd>
          </div>
          {mandat.bic && (
            <div>
              <dt className="text-xs text-gray-400">BIC</dt>
              <dd className="font-mono text-gray-800">{mandat.bic}</dd>
            </div>
          )}
          <div>
            <dt className="text-xs text-gray-400">Unterzeichnet am</dt>
            <dd className="text-gray-800">{new Date(mandat.unterzeichnet_am).toLocaleDateString('de-DE')}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-400">Status</dt>
            <dd>
              {mandat.aktiv
                ? <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">aktiv</span>
                : <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">inaktiv</span>
              }
            </dd>
          </div>
        </dl>
      )}

      {showForm && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="flex flex-col md:col-span-2">
              <label className={labelCls}>IBAN *</label>
              <IbanInput
                value={formData.iban}
                onChange={v => set('iban', v)}
                onBicFound={(bic) => { if (!formData.bic) set('bic', bic) }}
              />
              {konto.eigentuemer_ibans.length > 0 && (
                <select
                  className="mt-1 w-full text-xs border border-gray-200 rounded px-2 py-1 text-gray-500"
                  value=""
                  onChange={e => e.target.value && set('iban', e.target.value)}
                >
                  <option value="">Bekannte IBAN übernehmen…</option>
                  {konto.eigentuemer_ibans.map(iban => (
                    <option key={iban} value={iban}>{iban}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex flex-col">
              <label className={labelCls}>BIC</label>
              <input className={inputCls + ' font-mono'} value={formData.bic} onChange={e => set('bic', e.target.value)} placeholder="XXXXDEXX" />
            </div>
            <div className="flex flex-col">
              <label className={labelCls}>Unterzeichnet am *</label>
              <input type="date" className={inputCls} value={formData.unterzeichnet_am} onChange={e => set('unterzeichnet_am', e.target.value)} />
            </div>
            <div className="flex flex-col md:col-span-2">
              <label className={labelCls}>Mandatsreferenz *</label>
              <input className={inputCls + ' font-mono'} value={formData.mandatsreferenz} onChange={e => set('mandatsreferenz', e.target.value)} />
            </div>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Speichert…' : 'Speichern'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ebene 3: Buchungs-Detail (Teilbuchungen + zugeordnete Offene Posten)
// ---------------------------------------------------------------------------

function BuchungDetailView({
  personenkontoId,
  buchung,
  onBack,
}: {
  personenkontoId: string
  buchung: KontoauszugPosition
  onBack: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['buchung-detail', buchung.id],
    queryFn: () => buchhaltungApi.buchungDetail(personenkontoId, buchung.id),
  })

  const zugeordneteOPs: ZugeordneterOP[] = data?.zugeordnete_ops ?? []

  return (
    <div>
      <button onClick={onBack} className="flex items-center gap-2 text-sm text-blue-600 mb-4 hover:underline">
        ← Zurück zum Kontoauszug
      </button>

      {/* Kopf-Info */}
      <div className="bg-white rounded-lg border p-5 mb-4">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Buchungs-Detail</div>
            <h2 className="text-xl font-bold text-gray-900 font-mono">{buchung.bu_nr}</h2>
            <div className="text-sm text-gray-500 mt-1">{DATUM(buchung.buchungsdatum)}</div>
            <div className="text-sm text-gray-700 mt-1">{buchung.buchungstext}</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-400 mb-1">Gesamtbetrag</div>
            <div className="text-2xl font-bold tabular-nums text-gray-800">
              {EUR(buchung.soll ?? buchung.haben)}
            </div>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-gray-500 text-sm">Lade Detail…</div>
      ) : (
        <div className="space-y-4">

          {/* ─── Zugeordnete Offene Posten ─────────────────────────────── */}
          {zugeordneteOPs.length > 0 && (
            <div className="bg-white rounded-lg border overflow-hidden">
              <div className="px-4 py-3 bg-blue-50 border-b flex items-center gap-2">
                <span className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
                  Zugeordnete Offene Posten
                </span>
                <span className="text-xs text-blue-500">
                  — welche Forderungen mit dieser Zahlung getilgt wurden
                </span>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-gray-600 font-medium">OPOS-Nr.</th>
                    <th className="text-left px-4 py-2.5 text-gray-600 font-medium">Periode</th>
                    <th className="text-left px-4 py-2.5 text-gray-600 font-medium">Typ</th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium">Forderung</th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium">
                      Getilgt
                      <span className="block text-xs font-normal text-gray-400">(diese Buchung)</span>
                    </th>
                    <th className="text-right px-4 py-2.5 text-gray-600 font-medium">
                      Akt. Rest
                      <span className="block text-xs font-normal text-gray-400">(alle Zahlungen)</span>
                    </th>
                    <th className="text-center px-4 py-2.5 text-gray-600 font-medium w-24">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {zugeordneteOPs.map((op) => (
                    <>
                      <tr key={op.opos_nr} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-mono text-xs text-blue-700">{op.opos_nr}</td>
                        <td className="px-4 py-2.5 text-gray-700 whitespace-nowrap">{MONAT(op.periode)}</td>
                        <td className="px-4 py-2.5 text-gray-600">{op.sollstellungs_typ}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">{EUR(op.soll_betrag)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-green-700">
                          {EUR(op.betrag_tilgung)}
                        </td>
                        <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${op.saldo_nach > 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {EUR(op.saldo_nach)}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {op.vollstaendig_ausgeglichen ? (
                            <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                              ausgeglichen
                            </span>
                          ) : (
                            <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
                              offen
                            </span>
                          )}
                        </td>
                      </tr>
                      {/* Hinweiszeile wenn weitere Buchungen an dieser SS beteiligt sind */}
                      {op.betrag_weitere_zahlungen > 0 && (
                        <tr key={`${op.opos_nr}-weitere`} className="bg-blue-50/50">
                          <td colSpan={3} />
                          <td colSpan={4} className="px-4 py-1.5 text-xs text-blue-600 italic">
                            + {EUR(op.betrag_weitere_zahlungen)} durch weitere Buchung(en) — zusammen {EUR(op.betrag_tilgung + op.betrag_weitere_zahlungen)} von {EUR(op.soll_betrag)} getilgt
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
                {zugeordneteOPs.length > 1 && (
                  <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                    <tr>
                      <td colSpan={4} className="px-4 py-2.5 text-right font-semibold text-gray-700">
                        Gesamt getilgt (diese Buchung)
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-bold text-green-700">
                        {EUR(zugeordneteOPs.reduce((s, op) => s + op.betrag_tilgung, 0))}
                      </td>
                      <td colSpan={2} />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          )}

          {/* ─── Abrechnungsarten-Aufschlüsselung ─────────────────────── */}
          <div className="bg-white rounded-lg border overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Aufschlüsselung nach Abrechnungsart (Unterkonten)
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Soll (Unterkonto)</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Bezeichnung</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Haben (Erlöskonto)</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">BA</th>
                  <th className="text-right px-4 py-3 text-gray-600 font-medium">Betrag</th>
                </tr>
              </thead>
              <tbody>
                {(data?.positionen ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-400">
                      Keine Teilbuchungen vorhanden
                    </td>
                  </tr>
                ) : (data?.positionen ?? []).map(p => (
                  <tr key={p.id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono font-semibold text-blue-700">
                      {p.soll_unterkonto || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-gray-700">{p.soll_unterkonto_bezeichnung || '—'}</td>
                    <td className="px-4 py-2.5 font-mono text-gray-500">
                      {p.haben_konto}
                      {p.haben_konto_name && (
                        <span className="font-sans text-gray-400"> — {p.haben_konto_name}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="inline-block px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">
                        {p.ba}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-gray-800">
                      {EUR(p.betrag)}
                    </td>
                  </tr>
                ))}
              </tbody>
              {(data?.positionen ?? []).length > 0 && (
                <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                  <tr>
                    <td colSpan={4} className="px-4 py-3 text-right font-semibold text-gray-700">Gesamt</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold">
                      {EUR(data?.gesamt_betrag ?? 0)}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

        </div>
      )}
    </div>
  )
}
