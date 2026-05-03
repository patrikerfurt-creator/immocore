import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { mitarbeiterApi, zuordnungApi } from '../../api/mitarbeiter'
import { Badge } from '../../components/ui/Badge'
import { IbanInput } from '../../components/ui/IbanInput'
import { useObjektStore } from '../../stores/objekt'
import type { Objekt, Bankkonto } from '../../types'
import { ABTEILUNG_LABELS } from '../../types'

function MitarbeiterZuordnungSection({ objektId }: { objektId: string }) {
  const qc = useQueryClient()
  const [filterAbteilung, setFilterAbteilung] = useState<string>('')
  // aufgabe per mitarbeiter id
  const [selectedAufgabe, setSelectedAufgabe] = useState<Map<number, string>>(new Map())
  const [addingIds, setAddingIds] = useState<Set<number>>(new Set())
  // editing aufgabe for an existing zuordnung
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editAufgabe, setEditAufgabe] = useState<string>('')

  const { data: zuordnungen = [] } = useQuery({
    queryKey: ['mitarbeiter-zuordnungen', objektId],
    queryFn: () => zuordnungApi.listByObjekt(objektId),
    enabled: !!objektId,
  })

  const { data: alleMitarbeiter = [] } = useQuery({
    queryKey: ['mitarbeiter'],
    queryFn: () => mitarbeiterApi.list(),
  })

  const zugeordneteIds = new Set(zuordnungen.map(z => z.mitarbeiter_id))
  const nochNichtZugeordnet = alleMitarbeiter.filter(m => !zugeordneteIds.has(Number(m.id)))
  const gefiltertVerfuegbar = filterAbteilung
    ? nochNichtZugeordnet.filter(m => m.abteilungen.includes(filterAbteilung as never))
    : nochNichtZugeordnet

  const removeMut = useMutation({
    mutationFn: (id: number) => zuordnungApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mitarbeiter-zuordnungen', objektId] }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, aufgabe }: { id: number; aufgabe: string }) =>
      zuordnungApi.updateAufgabe(id, aufgabe),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mitarbeiter-zuordnungen', objektId] })
      setEditingId(null)
    },
  })

  const handleZuordnen = async (mitarbeiterId: number) => {
    const ma = nochNichtZugeordnet.find(m => Number(m.id) === mitarbeiterId)
    const aufgabe = selectedAufgabe.get(mitarbeiterId)
      ?? (ma?.abteilungen.length === 1 ? ma.abteilungen[0] : '')
    if (!aufgabe) return
    setAddingIds(prev => new Set(prev).add(mitarbeiterId))
    try {
      await zuordnungApi.create(mitarbeiterId, objektId, aufgabe)
      await qc.invalidateQueries({ queryKey: ['mitarbeiter-zuordnungen', objektId] })
      setSelectedAufgabe(prev => { const m = new Map(prev); m.delete(mitarbeiterId); return m })
    } finally {
      setAddingIds(prev => { const s = new Set(prev); s.delete(mitarbeiterId); return s })
    }
  }

  const setAufgabe = (mitarbeiterId: number, aufgabe: string) =>
    setSelectedAufgabe(prev => { const m = new Map(prev); m.set(mitarbeiterId, aufgabe); return m })

  const abteilungOptions = Object.entries(ABTEILUNG_LABELS) as [string, string][]

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
      <h2 className="font-semibold text-gray-700 mb-3">
        Mitarbeiter ({zuordnungen.length})
      </h2>

      {/* Zugeordnete Mitarbeiter */}
      {zuordnungen.length === 0 ? (
        <p className="text-sm text-gray-400 mb-4">Noch keine Mitarbeiter zugeordnet.</p>
      ) : (
        <div className="flex flex-col gap-2 mb-5">
          {zuordnungen.map(z => (
            <div key={z.id} className="flex items-center justify-between p-2.5 bg-gray-50 rounded border border-gray-100">
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium text-gray-800">{z.vollname}</span>
                <span className="ml-2 text-xs text-gray-400">{z.email}</span>
                <div className="mt-1">
                  {editingId === z.id ? (
                    <div className="flex items-center gap-2 mt-1">
                      <select
                        value={editAufgabe}
                        onChange={e => setEditAufgabe(e.target.value)}
                        className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:border-primary-500"
                      >
                        <option value="">— Aufgabe wählen —</option>
                        {z.abteilungen.map(a => (
                          <option key={a} value={a}>
                            {ABTEILUNG_LABELS[a as keyof typeof ABTEILUNG_LABELS] ?? a}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => updateMut.mutate({ id: z.id, aufgabe: editAufgabe })}
                        disabled={!editAufgabe || updateMut.isPending}
                        className="text-xs px-2 py-1 rounded bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                      >
                        Speichern
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs text-gray-400 hover:text-gray-600"
                      >
                        Abbrechen
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {z.aufgabe ? (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-primary-600 text-white font-medium">
                          {ABTEILUNG_LABELS[z.aufgabe as keyof typeof ABTEILUNG_LABELS] ?? z.aufgabe}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400 italic">Keine Aufgabe</span>
                      )}
                      <button
                        onClick={() => { setEditingId(z.id); setEditAufgabe(z.aufgabe) }}
                        className="text-xs text-gray-400 hover:text-primary-600"
                      >
                        ändern
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={() => removeMut.mutate(z.id)}
                disabled={removeMut.isPending}
                className="text-xs text-red-400 hover:text-red-600 ml-4 flex-shrink-0"
              >
                Entfernen
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Hinzufügen-Bereich */}
      {nochNichtZugeordnet.length > 0 && (
        <div className="border-t border-gray-100 pt-4 space-y-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Mitarbeiter hinzufügen</p>

          {/* Kategorie-Filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 flex-shrink-0">Kategorie:</label>
            <select
              value={filterAbteilung}
              onChange={e => { setFilterAbteilung(e.target.value) }}
              className="text-sm border border-gray-300 rounded px-2.5 py-1.5 focus:outline-none focus:border-primary-500"
            >
              <option value="">— Alle Kategorien —</option>
              {abteilungOptions.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>

          {/* Mitarbeiter-Liste */}
          {gefiltertVerfuegbar.length === 0 ? (
            <p className="text-xs text-gray-400">
              {filterAbteilung ? 'Keine weiteren Mitarbeiter in dieser Kategorie.' : 'Alle Mitarbeiter bereits zugeordnet.'}
            </p>
          ) : (
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              {gefiltertVerfuegbar.map(m => {
                const maId = Number(m.id)
                const aufgabe = selectedAufgabe.get(maId) ?? (m.abteilungen.length === 1 ? m.abteilungen[0] : '')
                const isAdding = addingIds.has(maId)
                return (
                  <div
                    key={m.id}
                    className="flex items-center gap-3 px-3 py-2.5 border-b border-gray-100 last:border-0"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-gray-800">{m.vollname}</span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {m.abteilungen.map(a => (
                          <span key={a} className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 border border-gray-200">
                            {ABTEILUNG_LABELS[a as keyof typeof ABTEILUNG_LABELS] ?? a}
                          </span>
                        ))}
                      </div>
                    </div>
                    <select
                      value={aufgabe}
                      onChange={e => setAufgabe(maId, e.target.value)}
                      className="text-sm border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:border-primary-500 flex-shrink-0"
                    >
                      {m.abteilungen.length > 1 && <option value="">Aufgabe wählen…</option>}
                      {m.abteilungen.map(a => (
                        <option key={a} value={a}>
                          {ABTEILUNG_LABELS[a as keyof typeof ABTEILUNG_LABELS] ?? a}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleZuordnen(maId)}
                      disabled={!aufgabe || isAdding}
                      className="text-xs px-3 py-1.5 rounded bg-primary-600 text-white font-medium hover:bg-primary-700 disabled:opacity-40 transition-colors flex-shrink-0"
                    >
                      {isAdding ? '…' : 'Zuordnen'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const ROLLEN_FREIGABE = [
  { value: 'auto',              label: 'Automatisch (keine Freigabe)' },
  { value: 'objektmanager',    label: 'Objektmanager' },
  { value: 'sachbearbeiter',   label: 'Sachbearbeiter' },
  { value: 'geschaeftsfuehrer', label: 'Geschäftsführer' },
]

const ROLLEN_LABEL: Record<string, string> = {
  auto: 'Automatisch',
  objektmanager: 'Objektmanager',
  sachbearbeiter: 'Sachbearbeiter',
  geschaeftsfuehrer: 'Geschäftsführer',
}

interface FreigabeStufe {
  bis: number | null
  rolle: string
  frist_tage: number
  beschreibung: string
}

const DEFAULT_STUFEN: FreigabeStufe[] = [
  { bis: 500,  rolle: 'auto',             frist_tage: 0, beschreibung: 'Automatische Freigabe' },
  { bis: 5000, rolle: 'objektmanager',    frist_tage: 3, beschreibung: 'Objektmanager-Freigabe' },
  { bis: null, rolle: 'geschaeftsfuehrer', frist_tage: 5, beschreibung: 'Geschäftsführer-Freigabe' },
]

function FreigabelimitsSection({ objektId, grenzen: initialGrenzen }: { objektId: string; grenzen: FreigabeStufe[] }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [stufen, setStufen] = useState<FreigabeStufe[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const startEdit = () => {
    setStufen(Array.isArray(initialGrenzen) && initialGrenzen.length > 0 ? initialGrenzen : DEFAULT_STUFEN)
    setEditing(true)
    setError(null)
  }

  const update = (idx: number, field: keyof FreigabeStufe, value: unknown) =>
    setStufen(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s))

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await objekteApi.update(objektId, { zahlungsfreigabe_grenzen: stufen } as never)
      await qc.invalidateQueries({ queryKey: ['objekte', objektId] })
      setEditing(false)
    } catch {
      setError('Speichern fehlgeschlagen.')
    } finally {
      setSaving(false)
    }
  }

  const grenzen = Array.isArray(initialGrenzen) && initialGrenzen.length > 0 ? initialGrenzen : []

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-gray-700">Freigabelimits (Eingangsrechnungen)</h2>
        {!editing && (
          <button onClick={startEdit} className="text-xs text-primary-600 hover:text-primary-800">
            Bearbeiten
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm min-w-[560px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-10">Stufe</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Bis (€)</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Freigabe durch</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Frist (Tage)</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Beschreibung</th>
                </tr>
              </thead>
              <tbody>
                {stufen.map((s, idx) => (
                  <tr key={idx} className="border-t border-gray-100">
                    <td className="px-3 py-2 text-gray-500 font-medium">{idx + 1}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          value={s.bis ?? ''}
                          onChange={e => update(idx, 'bis', e.target.value ? parseFloat(e.target.value) : null)}
                          className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 outline-none w-[100px]"
                          placeholder={idx === stufen.length - 1 ? '∞' : '0'}
                          min={0}
                        />
                        {idx === stufen.length - 1 && (
                          <span className="text-xs text-gray-400">(leer = unbegrenzt)</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={s.rolle}
                        onChange={e => update(idx, 'rolle', e.target.value)}
                        className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 outline-none"
                      >
                        {ROLLEN_FREIGABE.map(r => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        value={s.frist_tage}
                        onChange={e => update(idx, 'frist_tage', parseInt(e.target.value) || 0)}
                        className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 outline-none w-[70px]"
                        min={0}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={s.beschreibung}
                        onChange={e => update(idx, 'beschreibung', e.target.value)}
                        className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 outline-none w-full"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 rounded bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Speichert…' : 'Speichern'}
            </button>
            <button
              onClick={() => setEditing(false)}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5"
            >
              Abbrechen
            </button>
          </div>
        </div>
      ) : grenzen.length === 0 ? (
        <p className="text-sm text-gray-400">
          Keine Freigabelimits konfiguriert.{' '}
          <button onClick={startEdit} className="text-primary-600 hover:underline">Jetzt einrichten</button>
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm min-w-[500px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-600 w-10">Stufe</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600">Betrag</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600">Freigabe durch</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600">Frist</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600">Beschreibung</th>
              </tr>
            </thead>
            <tbody>
              {grenzen.map((s, idx) => {
                const prevBis = grenzen[idx - 1]?.bis
                const vonLabel = idx === 0 ? '0' : prevBis != null ? `${(prevBis + 1).toLocaleString('de-DE')}` : ''
                const bisLabel = s.bis != null ? s.bis.toLocaleString('de-DE') + ' €' : '∞'
                return (
                  <tr key={idx} className="border-t border-gray-100">
                    <td className="px-3 py-2 text-gray-500 font-medium">{idx + 1}</td>
                    <td className="px-3 py-2 text-gray-700 text-xs">
                      {s.bis != null ? `${vonLabel} – ${bisLabel}` : `ab ${vonLabel} €`}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        s.rolle === 'auto'             ? 'bg-green-50 text-green-700 border border-green-200' :
                        s.rolle === 'objektmanager'   ? 'bg-blue-50 text-blue-700 border border-blue-200' :
                        s.rolle === 'geschaeftsfuehrer' ? 'bg-orange-50 text-orange-700 border border-orange-200' :
                        'bg-gray-50 text-gray-600 border border-gray-200'
                      }`}>
                        {ROLLEN_LABEL[s.rolle] ?? s.rolle}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-600 text-xs">
                      {s.frist_tage === 0 ? 'Sofort' : `${s.frist_tage} Tage`}
                    </td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{s.beschreibung}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
      <h2 className="font-semibold text-gray-700 mb-3">{title}</h2>
      {children}
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-400">{label}</span>
      <span className="text-sm text-gray-800">{value ?? '–'}</span>
    </div>
  )
}

const inputCls = 'w-full text-sm border border-gray-300 rounded px-2.5 py-1.5 focus:outline-none focus:border-primary-500'
const labelCls = 'text-xs text-gray-400 mb-1'

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <label className={labelCls}>{label}</label>
      {children}
    </div>
  )
}

export function ObjektDetail() {
  const { id } = useParams<{ id: string }>()
  const setSelected = useObjektStore(s => s.setSelected)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['objekte', id],
    queryFn: () => objekteApi.get(id!),
    enabled: !!id,
  })
  const { data: belegungen = [] } = useQuery({
    queryKey: ['eigentumsverhaeltnisse', id, 'aktiv'],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ objekt: id!, aktiv: 'true' }),
    enabled: !!id,
  })
  const belegungByEinheit = Object.fromEntries(belegungen.map(b => [b.einheit, b.person_name]))

  useEffect(() => {
    if (id && data) setSelected(id, data.bezeichnung, data.objektnummer, data.objekt_typ)
  }, [id, data, setSelected])

  const [isEditing, setIsEditing] = useState(false)
  const [formData, setFormData] = useState<Partial<Objekt>>({})
  const [bankkontenEdits, setBankkontenEdits] = useState<Bankkonto[]>([])
  const [bankkontenDeleted, setBankkontenDeleted] = useState<string[]>([])
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const startEdit = () => {
    if (!data) return
    setFormData({
      bezeichnung: data.bezeichnung,
      objekt_typ: data.objekt_typ,
      strasse: data.strasse,
      plz: data.plz,
      ort: data.ort,
      baujahr: data.baujahr ?? undefined,
      verwaltung_seit: data.verwaltung_seit,
      wirtschaftsjahr_start: data.wirtschaftsjahr_start,
      umsatzsteuer_pflichtig: data.umsatzsteuer_pflichtig,
      glaeubiger_id: data.glaeubiger_id,
      status: data.status,
    })
    setBankkontenEdits(data.bankkonten ?? [])
    setBankkontenDeleted([])
    setSaveError(null)
    setIsEditing(true)
  }

  const set = (field: keyof Objekt, value: unknown) =>
    setFormData(prev => ({ ...prev, [field]: value }))

  const setBk = (idx: number, field: keyof Bankkonto, value: unknown) =>
    setBankkontenEdits(prev => prev.map((b, i) => i === idx ? { ...b, [field]: value } : b))

  const addBankkonto = () =>
    setBankkontenEdits(prev => [...prev, {
      id: `new-${Date.now()}`,
      objekt: id!,
      konto_typ: 'bewirtschaftung' as const,
      bezeichnung: '',
      iban: '',
      bic: '',
      kontoinhaber: '',
      reihenfolge: prev.length + 1,
      aktiv: true,
    }])

  const removeBankkonto = (idx: number) => {
    const bk = bankkontenEdits[idx]
    if (!bk.id.startsWith('new-')) {
      setBankkontenDeleted(prev => [...prev, bk.id])
    }
    setBankkontenEdits(prev => prev.filter((_, i) => i !== idx))
  }

  const handleSave = async () => {
    setIsSaving(true)
    setSaveError(null)
    try {
      await objekteApi.update(id!, formData)
      for (const bkId of bankkontenDeleted) {
        await objekteApi.deleteBankkonto(bkId)
      }
      for (const bk of bankkontenEdits) {
        if (bk.id.startsWith('new-')) {
          const { id: _id, ...rest } = bk
          await objekteApi.createBankkonto(rest)
        } else {
          await objekteApi.updateBankkonto(bk.id, bk)
        }
      }
      await queryClient.invalidateQueries({ queryKey: ['objekte', id] })
      queryClient.invalidateQueries({ queryKey: ['objekte'] })
      setIsEditing(false)
      setBankkontenDeleted([])
    } catch {
      setSaveError('Speichern fehlgeschlagen. Bitte prüfen Sie die Eingaben.')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) return <p className="text-gray-400">Laden…</p>
  if (!data) return <p className="text-gray-500">Objekt nicht gefunden.</p>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/objekte" className="text-primary-600 hover:underline text-sm">← Objekte</Link>
        <span className="text-gray-300">|</span>
        <h1 className="text-2xl font-bold text-gray-900">{data.bezeichnung}</h1>
        <Badge value={data.objekt_typ} />
        <Badge value={data.status} />
        <div className="ml-auto">
          {!isEditing && (
            <button
              onClick={startEdit}
              className="bg-primary-600 text-white px-3 py-1.5 rounded text-sm hover:bg-primary-700 transition-colors"
            >
              Bearbeiten
            </button>
          )}
        </div>
      </div>

      {/* ── Stammdaten ────────────────────────────────────────────── */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
        <h2 className="font-semibold text-gray-700 mb-3">Stammdaten</h2>

        {isEditing ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <EditField label="Bezeichnung *">
                <input
                  className={inputCls}
                  value={formData.bezeichnung ?? ''}
                  onChange={e => set('bezeichnung', e.target.value)}
                />
              </EditField>

              <EditField label="Typ *">
                <select className={inputCls} value={formData.objekt_typ ?? ''} onChange={e => set('objekt_typ', e.target.value)}>
                  <option value="WEG">WEG</option>
                  <option value="ZH">ZH</option>
                  <option value="SEV">SEV</option>
                </select>
              </EditField>

              <EditField label="Status">
                <select className={inputCls} value={formData.status ?? ''} onChange={e => set('status', e.target.value)}>
                  <option value="aktiv">Aktiv</option>
                  <option value="archiviert">Archiviert</option>
                </select>
              </EditField>

              <EditField label="Baujahr">
                <input
                  type="number"
                  className={inputCls}
                  value={formData.baujahr ?? ''}
                  onChange={e => set('baujahr', e.target.value ? parseInt(e.target.value) : null)}
                />
              </EditField>

              <EditField label="Straße *">
                <input
                  className={inputCls}
                  value={formData.strasse ?? ''}
                  onChange={e => set('strasse', e.target.value)}
                />
              </EditField>

              <EditField label="PLZ *">
                <input
                  className={inputCls}
                  value={formData.plz ?? ''}
                  onChange={e => set('plz', e.target.value)}
                />
              </EditField>

              <EditField label="Ort *">
                <input
                  className={inputCls}
                  value={formData.ort ?? ''}
                  onChange={e => set('ort', e.target.value)}
                />
              </EditField>

              <EditField label="Verw. seit *">
                <input
                  type="date"
                  className={inputCls}
                  value={formData.verwaltung_seit ?? ''}
                  onChange={e => set('verwaltung_seit', e.target.value)}
                />
              </EditField>

              <EditField label="WJ-Start (Monat)">
                <input
                  type="number"
                  min={1}
                  max={12}
                  className={inputCls}
                  value={formData.wirtschaftsjahr_start ?? ''}
                  onChange={e => set('wirtschaftsjahr_start', parseInt(e.target.value))}
                />
              </EditField>

              <EditField label="USt-pflichtig">
                <select
                  className={inputCls}
                  value={formData.umsatzsteuer_pflichtig ? 'ja' : 'nein'}
                  onChange={e => set('umsatzsteuer_pflichtig', e.target.value === 'ja')}
                >
                  <option value="nein">Nein</option>
                  <option value="ja">Ja</option>
                </select>
              </EditField>

              <EditField label="Gläubiger-ID (SEPA)">
                <input
                  className={inputCls}
                  value={formData.glaeubiger_id ?? ''}
                  onChange={e => set('glaeubiger_id', e.target.value)}
                  placeholder="z.B. DE98ZZZ09999999999"
                />
              </EditField>
            </div>

            {saveError && (
              <p className="text-sm text-red-600">{saveError}</p>
            )}

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="bg-primary-600 text-white px-4 py-1.5 rounded text-sm hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                {isSaving ? 'Speichert…' : 'Speichern'}
              </button>
              <button
                onClick={() => { setIsEditing(false); setBankkontenDeleted([]); setSaveError(null) }}
                disabled={isSaving}
                className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5"
              >
                Abbrechen
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Field label="Objektnummer" value={data.objektnummer} />
            <Field label="Typ" value={data.objekt_typ} />
            <Field label="Baujahr" value={data.baujahr} />
            <Field label="Verw. seit" value={data.verwaltung_seit} />
            <Field label="Straße" value={data.strasse} />
            <Field label="PLZ / Ort" value={`${data.plz} ${data.ort}`} />
            <Field label="WJ-Start" value={`Monat ${data.wirtschaftsjahr_start}`} />
            <Field label="USt-pflichtig" value={data.umsatzsteuer_pflichtig ? 'Ja' : 'Nein'} />
            <Field label="Gläubiger-ID (SEPA)" value={data.glaeubiger_id || '–'} />
          </div>
        )}
      </div>

      {/* ── Eingänge ──────────────────────────────────────────────── */}
      {data.eingaenge?.length > 0 && (
        <Section title={`Eingänge (${data.eingaenge.length})`}>
          <div className="flex flex-col gap-2">
            {data.eingaenge.map(e => (
              <div key={e.id} className="text-sm text-gray-700">
                {e.strasse}, {e.plz} {e.ort}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Einheiten ─────────────────────────────────────────────── */}
      <Section title={`Einheiten (${data.einheiten.length})`}>
        {data.einheiten.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Einheiten erfasst.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-2 font-medium text-gray-600">Fl.-Nr.</th>
                <th className="text-left py-2 font-medium text-gray-600">Bez. Einheit</th>
                <th className="text-left py-2 font-medium text-gray-600">Lage</th>
                <th className="text-left py-2 font-medium text-gray-600">Typ</th>
                <th className="text-left py-2 font-medium text-gray-600">Aktuelle Belegung</th>
              </tr>
            </thead>
            <tbody>
              {data.einheiten.map(e => (
                <tr key={e.id} className="border-b border-gray-50">
                  <td className="py-2 font-mono text-gray-700">{e.flaechennummer || '–'}</td>
                  <td className="py-2 text-gray-800 font-medium">{e.einheit_nr}</td>
                  <td className="py-2 text-gray-600">{e.lage || '–'}</td>
                  <td className="py-2 text-gray-600">{e.einheit_typ}</td>
                  <td className="py-2 text-gray-600">{belegungByEinheit[e.id] ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {/* ── Bankkonten ────────────────────────────────────────────── */}
      <Section title={`Bankkonten (${isEditing ? bankkontenEdits.length : data.bankkonten.length})`}>
        {isEditing ? (
          <div className="flex flex-col gap-3">
            {bankkontenEdits.map((bk, idx) => (
              <div key={bk.id} className="p-3 bg-gray-50 rounded border border-gray-100 flex flex-col gap-2">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <EditField label="Bezeichnung *">
                    <input className={inputCls} value={bk.bezeichnung} onChange={e => setBk(idx, 'bezeichnung', e.target.value)} />
                  </EditField>
                  <EditField label="Typ">
                    <select className={inputCls} value={bk.konto_typ} onChange={e => setBk(idx, 'konto_typ', e.target.value)}>
                      <option value="bewirtschaftung">Bewirtschaftung</option>
                      <option value="ruecklage">Rücklage</option>
                    </select>
                  </EditField>
                  <EditField label="IBAN">
                    <IbanInput
                      value={bk.iban}
                      onChange={v => setBk(idx, 'iban', v)}
                      onBicFound={(bic) => { if (!bk.bic) setBk(idx, 'bic', bic) }}
                    />
                  </EditField>
                  <EditField label="BIC">
                    <input className={inputCls} value={bk.bic} onChange={e => setBk(idx, 'bic', e.target.value)} placeholder="wird automatisch befüllt" />
                  </EditField>
                  <EditField label="Kontoinhaber">
                    <input className={inputCls} value={bk.kontoinhaber ?? ''} onChange={e => setBk(idx, 'kontoinhaber', e.target.value)} />
                  </EditField>
                  <EditField label="Reihenfolge">
                    <input type="number" min={1} className={inputCls} value={bk.reihenfolge} onChange={e => setBk(idx, 'reihenfolge', parseInt(e.target.value) || 1)} />
                  </EditField>
                  <EditField label="Aktiv">
                    <select className={inputCls} value={bk.aktiv ? 'ja' : 'nein'} onChange={e => setBk(idx, 'aktiv', e.target.value === 'ja')}>
                      <option value="ja">Ja</option>
                      <option value="nein">Nein</option>
                    </select>
                  </EditField>
                </div>
                <div className="flex justify-end">
                  <button type="button" onClick={() => removeBankkonto(idx)} className="text-xs text-red-500 hover:text-red-700">
                    Bankkonto entfernen
                  </button>
                </div>
              </div>
            ))}
            <button type="button" onClick={addBankkonto} className="text-sm text-primary-600 hover:text-primary-800 mt-1">
              + Bankkonto hinzufügen
            </button>
          </div>
        ) : data.bankkonten.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Bankkonten erfasst.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {data.bankkonten.map(b => (
              <div key={b.id} className="flex items-center justify-between p-3 bg-gray-50 rounded border border-gray-100">
                <div>
                  <p className="text-sm font-medium text-gray-800">{b.bezeichnung}</p>
                  <p className="text-xs text-gray-500 font-mono">{b.iban}</p>
                </div>
                <Badge value={b.konto_typ} label={b.konto_typ === 'bewirtschaftung' ? 'Bewirtschaftung' : 'Rücklage'} />
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── Freigabelimits ───────────────────────────────────────── */}
      <FreigabelimitsSection objektId={id!} grenzen={(data.zahlungsfreigabe_grenzen ?? []) as FreigabeStufe[]} />

      {/* ── Mitarbeiter-Zuordnung ─────────────────────────────────── */}
      <MitarbeiterZuordnungSection objektId={id!} />

      <div className="flex gap-3 mt-4 flex-wrap">
        <Link to={`/buchhaltung?objekt=${id}`} className="text-sm text-primary-600 hover:underline">Buchungsjournal →</Link>
        <Link to={`/stammdaten/kontenplan?objekt=${id}`} className="text-sm text-primary-600 hover:underline">Kontenplan →</Link>
        <Link to={`/stammdaten/verteilerschluessel?objekt=${id}`} className="text-sm text-primary-600 hover:underline">Verteilerschlüssel →</Link>
        <Link to={`/rechnungen?objekt=${id}`} className="text-sm text-primary-600 hover:underline">Rechnungen →</Link>
        <Link to={`/tickets?objekt=${id}`} className="text-sm text-primary-600 hover:underline">Tickets →</Link>
      </div>
    </div>
  )
}
