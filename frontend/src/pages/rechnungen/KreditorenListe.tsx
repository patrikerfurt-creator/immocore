import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import { handwerkerApi } from '../../api/handwerker'
import { Button } from '../../components/ui/Button'
import { IbanInput } from '../../components/ui/IbanInput'
import type { Gewerk, Kreditor } from '../../types'

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
  rechnung_id?: string | null
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
// Typen Buchungszeile
// ---------------------------------------------------------------------------
interface KreditorBuchungszeile {
  id: string
  bu_nr: string
  buchungsdatum: string
  buchungstext: string | null
  gegenkonto: string
  soll: number | null
  haben: number | null
  saldo: number
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
  const navigate = useNavigate()
  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 6 }, (_, i) => currentYear - i)
  const [selectedJahr, setSelectedJahr] = useState('')
  const [activeTab, setActiveTab] = useState<'opos' | 'buchungen'>('opos')

  const { data, isLoading } = useQuery({
    queryKey: ['kreditor-kontoauszug', kreditor.id, selectedJahr],
    queryFn: () => rechnungenApi.kreditorKontoauszug(kreditor.id, selectedJahr ? { jahr: selectedJahr } : {}),
  })

  const positionen: KreditorKontoPosition[] = data?.positionen ?? []
  const buchungen: KreditorBuchungszeile[] = data?.buchungen ?? []
  const buchungenSaldo: number = data?.buchungen_saldo ?? 0
  const kreditorkonto_nr: string = data?.kreditorkonto_nr ?? ''

  const gesamtOffen = positionen
    .filter(p => p.status !== 'bezahlt' && p.status !== 'storniert' && p.betrag_offen != null)
    .reduce((s, p) => s + (p.betrag_offen ?? 0), 0)

  const tabClass = (t: 'opos' | 'buchungen') =>
    `px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
      activeTab === t
        ? 'border-indigo-600 text-indigo-700'
        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
    }`

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 overflow-y-auto py-10">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-5xl mx-4">
        {/* Header */}
        <div className="flex justify-between items-start p-6 border-b">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Kreditorenkonto</h2>
            <p className="text-gray-500 text-sm mt-0.5">
              {kreditor.name}
              {kreditorkonto_nr && (
                <span className="ml-2 font-mono text-xs text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">
                  {kreditorkonto_nr}
                </span>
              )}
            </p>
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
            <span className="text-gray-500">Rechnungen / OPs</span>
            <span className="ml-2 font-semibold text-gray-800">{positionen.length}</span>
          </div>
          <div>
            <span className="text-gray-500">Offene Verbindlichkeiten</span>
            <span className="ml-2 font-semibold text-orange-700">{fmtEur(gesamtOffen)}</span>
          </div>
          {buchungen.length > 0 && (
            <div>
              <span className="text-gray-500">Buchungssaldo {kreditorkonto_nr}</span>
              <span className={`ml-2 font-semibold ${buchungenSaldo < 0 ? 'text-blue-700' : buchungenSaldo > 0 ? 'text-gray-800' : 'text-gray-400'}`}>
                {fmtEur(Math.abs(buchungenSaldo))}
                <span className="text-xs font-normal text-gray-400 ml-1">
                  {buchungenSaldo > 0 ? 'S' : buchungenSaldo < 0 ? 'H' : ''}
                </span>
              </span>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b px-6">
          <button className={tabClass('opos')} onClick={() => setActiveTab('opos')}>
            OPOS / Rechnungen
            <span className="ml-1.5 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{positionen.length}</span>
          </button>
          <button className={tabClass('buchungen')} onClick={() => setActiveTab('buchungen')}>
            Buchungszeilen
            {kreditorkonto_nr && (
              <span className="ml-1.5 font-mono text-xs text-indigo-500">({kreditorkonto_nr})</span>
            )}
            <span className="ml-1.5 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{buchungen.length}</span>
          </button>
        </div>

        {/* Tab-Inhalt */}
        <div className="p-6">
          {isLoading ? (
            <div className="text-gray-400 text-sm text-center py-10">Lade Kontoauszug…</div>
          ) : activeTab === 'opos' ? (
            /* ── Tab: OPOS / Rechnungen ── */
            positionen.length === 0 ? (
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
                    <tr
                      key={p.id}
                      className={`border-t hover:bg-gray-50 ${p.herkunft === 'wkz' ? 'bg-blue-50/30' : ''} ${p.rechnung_id ? 'cursor-pointer' : ''}`}
                      onClick={() => {
                        if (p.rechnung_id) {
                          onClose()
                          navigate(`/rechnungen/${p.rechnung_id}/prueffall`)
                        }
                      }}
                    >
                      <td className="px-3 py-2 font-mono text-xs text-blue-700 font-semibold">
                        {p.opos_nr ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        <div className="flex items-center gap-1.5">
                          {p.herkunft === 'wkz' && (
                            <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium shrink-0">WKZ</span>
                          )}
                          <span className="truncate max-w-xs" title={p.rechnungsnummer ?? undefined}>{p.rechnungsnummer || '—'}</span>
                          {p.rechnung_id && (
                            <span className="text-xs text-gray-400 shrink-0">↗</span>
                          )}
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
            )
          ) : (
            /* ── Tab: Buchungszeilen (Soll/Haben) ── */
            buchungen.length === 0 ? (
              <div className="text-gray-400 text-sm text-center py-10">
                {kreditorkonto_nr
                  ? `Keine Buchungen auf Konto ${kreditorkonto_nr} vorhanden.`
                  : 'Dieser Kreditor hat noch keine Kreditorennummer — bitte zuerst vergeben.'}
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-3 py-2 text-gray-500 font-medium w-36">BU-Nr.</th>
                    <th className="text-left px-3 py-2 text-gray-500 font-medium w-28">Datum</th>
                    <th className="text-left px-3 py-2 text-gray-500 font-medium w-40">Gegenkonto</th>
                    <th className="text-left px-3 py-2 text-gray-500 font-medium">Buchungstext</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-medium w-28">Soll</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-medium w-28">Haben</th>
                    <th className="text-right px-3 py-2 text-gray-500 font-medium w-28">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {buchungen.map(b => (
                    <tr key={b.id} className="border-t hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono text-xs text-gray-500">{b.bu_nr}</td>
                      <td className="px-3 py-2 text-gray-700 whitespace-nowrap">{fmt(b.buchungsdatum)}</td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-600 truncate max-w-0">{b.gegenkonto}</td>
                      <td className="px-3 py-2 text-gray-800 truncate max-w-xs">{b.buchungstext || '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-800">
                        {b.soll != null ? fmtEur(b.soll) : ''}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-blue-700">
                        {b.haben != null ? fmtEur(b.haben) : ''}
                      </td>
                      <td className={`px-3 py-2 text-right tabular-nums font-semibold ${
                        b.saldo > 0 ? 'text-gray-800' : b.saldo < 0 ? 'text-blue-700' : 'text-gray-400'
                      }`}>
                        {fmtEur(Math.abs(b.saldo))}
                        <span className="text-xs font-normal text-gray-400 ml-0.5">
                          {b.saldo > 0 ? 'S' : b.saldo < 0 ? 'H' : ''}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                  <tr>
                    <td colSpan={4} className="px-3 py-3 text-right font-semibold text-gray-700 text-sm">
                      Abschlusssaldo
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums font-bold text-gray-800">
                      {buchungenSaldo > 0 ? fmtEur(buchungenSaldo) : ''}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums font-bold text-blue-700">
                      {buchungenSaldo < 0 ? fmtEur(Math.abs(buchungenSaldo)) : ''}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            )
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

  const { data: gewerkeOptionen } = useQuery({
    queryKey: ['gewerke'],
    queryFn: handwerkerApi.gewerke,
  })

  const ausgewaehlteGewerke = form.gewerke ?? []
  const toggleGewerk = (id: string) =>
    setForm(prev => {
      const bisher = prev.gewerke ?? []
      const neu = bisher.includes(id) ? bisher.filter(g => g !== id) : [...bisher, id]
      return { ...prev, gewerke: neu }
    })

  const zeigtHandwerkerHinweis = !!form.ist_handwerker && !form.email

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
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Ansprechpartner</label>
          <input type="text" value={form.kontakt_person ?? ''} onChange={set('kontakt_person')}
                 className="border rounded-lg px-3 py-2 text-sm w-full" />
        </div>
      </div>

      <div className="border-t mt-4 pt-4">
        <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <input
            type="checkbox"
            checked={!!form.ist_handwerker}
            onChange={e => setForm(prev => ({ ...prev, ist_handwerker: e.target.checked }))}
          />
          Ist Handwerker
        </label>

        {form.ist_handwerker && (
          <div className="mt-3">
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Gewerke</label>
            <div className="flex flex-wrap gap-3">
              {(gewerkeOptionen ?? []).map((g: Gewerk) => (
                <label key={g.id} className="flex items-center gap-1.5 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={ausgewaehlteGewerke.includes(g.id)}
                    onChange={() => toggleGewerk(g.id)}
                  />
                  {g.bezeichnung}
                </label>
              ))}
              {(gewerkeOptionen ?? []).length === 0 && (
                <p className="text-xs text-gray-400">Keine Gewerke gepflegt.</p>
              )}
            </div>
          </div>
        )}

        {zeigtHandwerkerHinweis && (
          <p className="text-xs text-red-600 mt-2">
            Ohne E-Mail-Adresse kann dieser Kreditor nicht als Handwerker beauftragt werden.
          </p>
        )}
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
interface KredFilters {
  name: string; kreditorennummer: string; iban: string; ort: string; email: string; rechnungen: string
  ist_handwerker: '' | 'ja' | 'nein'
  gewerk: string
}
const KRED_EMPTY: KredFilters = {
  name: '', kreditorennummer: '', iban: '', ort: '', email: '', rechnungen: '',
  ist_handwerker: '', gewerk: '',
}
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

  const { data: gewerkeOptionen } = useQuery({
    queryKey: ['gewerke'],
    queryFn: handwerkerApi.gewerke,
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
    (filters.rechnungen === '' || String(r.rechnungen_anzahl).includes(filters.rechnungen)) &&
    (filters.ist_handwerker === '' || (filters.ist_handwerker === 'ja' ? r.ist_handwerker : !r.ist_handwerker)) &&
    (filters.gewerk === '' || (r.gewerke ?? []).includes(filters.gewerk)),
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
                  <th className="text-left px-3 py-2 text-gray-500 font-medium whitespace-nowrap">Handwerker</th>
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
                  <td className="px-3 py-1">
                    <div className="flex flex-col gap-1">
                      <select
                        value={filters.ist_handwerker}
                        onChange={e => setFilters(prev => ({ ...prev, ist_handwerker: e.target.value as KredFilters['ist_handwerker'] }))}
                        className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-400"
                      >
                        <option value="">Alle</option>
                        <option value="ja">Nur Handwerker</option>
                        <option value="nein">Keine Handwerker</option>
                      </select>
                      <select
                        value={filters.gewerk}
                        onChange={e => setFilter('gewerk', e.target.value)}
                        className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-400"
                      >
                        <option value="">Alle Gewerke</option>
                        {(gewerkeOptionen ?? []).map((g: Gewerk) => (
                          <option key={g.id} value={g.id}>{g.bezeichnung}</option>
                        ))}
                      </select>
                    </div>
                  </td>
                  <td className="px-3 py-1">{fi('rechnungen')}</td>
                  <td />
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-10 text-gray-400">
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
                      <td className="px-3 py-2.5">
                        {k.ist_handwerker ? (
                          <div className="flex flex-col gap-1 items-start">
                            <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">
                              Handwerker
                            </span>
                            {k.gewerke_bezeichnungen.length > 0 && (
                              <span className="text-xs text-gray-500">{k.gewerke_bezeichnungen.join(', ')}</span>
                            )}
                            {!k.email && (
                              <span className="text-xs text-red-600">Ohne E-Mail nicht beauftragbar</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
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
