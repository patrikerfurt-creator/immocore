import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { vorgaengeApi } from '../../api/vorgaenge'
import { objekteApi } from '../../api/objekte'
import { personenApi } from '../../api/personen'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { PersonList, VorgangCreatePayload, VorgangPrioritaet } from '../../types'

const STATUS_OPTIONEN = [
  { value: 'offen', label: 'Offen' },
  { value: 'in_bearbeitung', label: 'In Bearbeitung' },
  { value: 'wartet_extern', label: 'Wartet auf Dritte' },
  { value: 'wiedervorlage', label: 'Wiedervorlage' },
  { value: 'erledigt', label: 'Erledigt' },
  { value: 'storniert', label: 'Storniert' },
]

const QUELLE_OPTIONEN = [
  { value: 'manuell', label: 'Manuell' },
  { value: 'mail', label: 'E-Mail' },
  { value: 'telefon', label: 'Telefon' },
  { value: 'beschluss', label: 'Beschluss' },
  { value: 'portal', label: 'Eigentümer-Portal' },
]

function PersonAuswahl({ onSelect }: { onSelect: (p: PersonList) => void }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: treffer } = useQuery({
    queryKey: ['vorgaenge-personen-suche', query],
    queryFn: () => personenApi.list({ search: query }),
    enabled: query.length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => {
    function onClickAway(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickAway)
    return () => document.removeEventListener('mousedown', onClickAway)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <Input
        label="Person (Melder/Ansprechpartner)"
        placeholder="Name eingeben…"
        value={query}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
      />
      {open && treffer && treffer.length > 0 && (
        <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded shadow-lg max-h-48 overflow-y-auto">
          {treffer.map(p => (
            <button
              key={p.id}
              type="button"
              className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
              onClick={() => { onSelect(p); setQuery(p.name); setOpen(false) }}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function VorgaengeListe() {
  const [searchParams] = useSearchParams()
  const [objektFilter, setObjektFilter] = useState(searchParams.get('objekt') ?? '')
  const [statusFilter, setStatusFilter] = useState('')
  const [typFilter, setTypFilter] = useState('')
  const [quelleFilter, setQuelleFilter] = useState('')
  const [showForm, setShowForm] = useState(false)

  const [form, setForm] = useState<VorgangCreatePayload>({
    typ: '', objekt: '', einheit: '', person: '', betreff: '', beschreibung: '',
    prioritaet: 'normal',
  })
  const [personName, setPersonName] = useState('')
  // true = Person wurde vom Nutzer bewusst gewählt/entfernt, false = Person kommt (noch) aus der
  // automatischen Eigentümer-Vorbelegung und darf von dieser aktualisiert werden.
  const [personIstManuell, setPersonIstManuell] = useState(false)
  const vorherigeEinheitRef = useRef<string>('')

  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: typen } = useQuery({ queryKey: ['vorgang-typen'], queryFn: vorgaengeApi.typenListe })
  const { data: einheitenFuerForm } = useQuery({
    queryKey: ['einheiten-fuer-vorgang', form.objekt],
    queryFn: () => objekteApi.listEinheiten({ objekt: form.objekt as string }),
    enabled: !!form.objekt,
  })

  // Aktuelles Eigentumsverhältnis der gewählten Einheit laden (für Melder-Vorbelegung).
  const einheitId = (form.einheit as string) || ''
  const {
    data: eigentuemerListe,
    isFetching: eigentuemerLaedt,
    isError: eigentuemerFehler,
  } = useQuery({
    queryKey: ['einheit-eigentuemer', einheitId],
    queryFn: () => personenApi.eigentumsverhaeltnisse({ einheit: einheitId, aktiv: 'true' }),
    enabled: !!einheitId,
    staleTime: 30_000,
  })

  // Beim Wechsel der Einheit: auf eine andere Einheit -> zurück in den Automatik-Modus
  // (neue Vorbelegung soll greifen). Einheit geleert -> nur die Automatik-Vorbelegung entfernen,
  // eine manuell gewählte Person bleibt stehen.
  useEffect(() => {
    if (einheitId === vorherigeEinheitRef.current) return
    vorherigeEinheitRef.current = einheitId
    if (!einheitId) {
      if (!personIstManuell) {
        setForm(f => ({ ...f, person: '' }))
        setPersonName('')
      }
      return
    }
    setPersonIstManuell(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [einheitId])

  // Sobald der aktuelle Eigentümer der Einheit geladen ist und die Person nicht manuell
  // gewählt wurde, Melder automatisch vorbelegen (inkl. sichtbarem Namen).
  useEffect(() => {
    if (!einheitId || personIstManuell || !eigentuemerListe) return
    const aktuellerEigentuemer = eigentuemerListe[0]
    if (aktuellerEigentuemer) {
      setForm(f => (f.person === aktuellerEigentuemer.person ? f : { ...f, person: aktuellerEigentuemer.person }))
      setPersonName(aktuellerEigentuemer.person_name)
    } else {
      setForm(f => (f.person ? { ...f, person: '' } : f))
      setPersonName('')
    }
  }, [eigentuemerListe, einheitId, personIstManuell])

  const { data: vorgaenge, isLoading } = useQuery({
    queryKey: ['vorgaenge', objektFilter, statusFilter, typFilter, quelleFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektFilter) params.objekt = objektFilter
      if (statusFilter) params.status = statusFilter
      if (typFilter) params.typ = typFilter
      if (quelleFilter) params.quelle = quelleFilter
      return vorgaengeApi.list(params)
    },
  })

  const createMutation = useMutation({
    mutationFn: () => vorgaengeApi.create({
      ...form,
      objekt: form.objekt || null,
      einheit: form.einheit || null,
      person: form.person || null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vorgaenge'] })
      setShowForm(false)
      setForm({ typ: '', objekt: '', einheit: '', person: '', betreff: '', beschreibung: '', prioritaet: 'normal' })
      setPersonName('')
      setPersonIstManuell(false)
      vorherigeEinheitRef.current = ''
    },
  })

  const ausgewaehlterTyp = typen?.find(t => t.id === form.typ)

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Vorgänge</h1>
        <Button onClick={() => setShowForm(v => !v)}>+ Vorgang erstellen</Button>
      </div>

      {createMutation.isError && (
        <p className="text-red-600 text-sm mb-4">
          {/* @ts-expect-error axios error shape */}
          {createMutation.error?.response?.data?.detail ?? 'Fehler beim Anlegen des Vorgangs.'}
        </p>
      )}

      {showForm && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 max-w-lg">
          <h2 className="font-semibold text-gray-700 mb-4">Neuer Vorgang</h2>
          <div className="flex flex-col gap-3">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Typ</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={form.typ}
                onChange={e => {
                  const typId = e.target.value
                  const typ = typen?.find(t => t.id === typId)
                  setForm(f => ({ ...f, typ: typId, prioritaet: typ?.standard_prioritaet ?? f.prioritaet }))
                }}
              >
                <option value="">Typ wählen…</option>
                {typen?.map(t => (
                  <option key={t.id} value={t.id}>{t.bezeichnung}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Objekt</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={form.objekt ?? ''}
                onChange={e => setForm(f => ({ ...f, objekt: e.target.value, einheit: '' }))}
              >
                <option value="">Objekt wählen…</option>
                {objekte?.map(o => (
                  <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
                ))}
              </select>
            </div>

            {form.objekt && (
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Einheit (optional)</label>
                <select
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={form.einheit ?? ''}
                  onChange={e => setForm(f => ({ ...f, einheit: e.target.value }))}
                >
                  <option value="">Keine Einheit</option>
                  {einheitenFuerForm?.map(e => (
                    <option key={e.id} value={e.id}>{e.einheit_nr}</option>
                  ))}
                </select>
              </div>
            )}

            <PersonAuswahl onSelect={p => {
              setForm(f => ({ ...f, person: p.id }))
              setPersonName(p.name)
              setPersonIstManuell(true)
            }} />
            {einheitId && eigentuemerLaedt && !personIstManuell && (
              <p className="text-xs text-gray-400">Lade aktuellen Eigentümer…</p>
            )}
            {einheitId && !eigentuemerLaedt && !eigentuemerFehler && eigentuemerListe?.length === 0 && !personIstManuell && (
              <p className="text-xs text-gray-400">Kein aktives Eigentumsverhältnis für diese Einheit gefunden.</p>
            )}
            {form.person && (
              <p className="text-xs text-gray-500">
                Ausgewählt: {personName}
                {!personIstManuell && <span className="text-gray-400"> (automatisch: aktueller Eigentümer)</span>}{' '}
                <button
                  type="button"
                  className="text-primary-600 hover:underline"
                  onClick={() => {
                    setForm(f => ({ ...f, person: '' }))
                    setPersonName('')
                    setPersonIstManuell(true)
                  }}
                >
                  entfernen
                </button>
              </p>
            )}

            <Input
              label="Betreff"
              value={form.betreff}
              onChange={e => setForm(f => ({ ...f, betreff: e.target.value }))}
            />
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Beschreibung</label>
              <textarea
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
                value={form.beschreibung ?? ''}
                onChange={e => setForm(f => ({ ...f, beschreibung: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Priorität</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={form.prioritaet}
                onChange={e => setForm(f => ({ ...f, prioritaet: e.target.value as VorgangPrioritaet }))}
              >
                <option value="niedrig">Niedrig</option>
                <option value="normal">Normal</option>
                <option value="hoch">Hoch</option>
              </select>
              {ausgewaehlterTyp && (
                <p className="text-xs text-gray-400 mt-1">
                  Vorbelegt aus Typ „{ausgewaehlterTyp.bezeichnung}“ — kann überschrieben werden.
                </p>
              )}
            </div>

            <div className="flex gap-2 mt-2">
              <Button
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending || !form.typ || !form.betreff || (!form.objekt && !form.einheit && !form.person)}
              >
                Erstellen
              </Button>
              <Button variant="secondary" onClick={() => setShowForm(false)}>Abbrechen</Button>
            </div>
            {!form.objekt && !form.einheit && !form.person && (
              <p className="text-xs text-gray-400">Mindestens Objekt, Einheit oder Person muss gewählt sein.</p>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 mb-4">
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={objektFilter}
          onChange={e => setObjektFilter(e.target.value)}
        >
          <option value="">Alle Objekte</option>
          {objekte?.map(o => (
            <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">Alle Status</option>
          {STATUS_OPTIONEN.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={typFilter}
          onChange={e => setTypFilter(e.target.value)}
        >
          <option value="">Alle Typen</option>
          {typen?.map(t => (
            <option key={t.id} value={t.id}>{t.bezeichnung}</option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={quelleFilter}
          onChange={e => setQuelleFilter(e.target.value)}
        >
          <option value="">Alle Quellen</option>
          {QUELLE_OPTIONEN.map(q => (
            <option key={q.value} value={q.value}>{q.label}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Nummer</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Betreff</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Typ</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Objekt</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Priorität</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Zugewiesen</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Erstellt am</th>
              </tr>
            </thead>
            <tbody>
              {vorgaenge?.map(v => (
                <tr key={v.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/vorgaenge/${v.id}`} className="text-primary-600 hover:underline font-mono text-xs">
                      {v.nummer}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-800">{v.betreff}</td>
                  <td className="px-4 py-3">{v.typ_bezeichnung}</td>
                  <td className="px-4 py-3 text-gray-600">{v.objekt_bezeichnung ?? v.person_name ?? '–'}</td>
                  <td className="px-4 py-3"><Badge value={v.prioritaet} /></td>
                  <td className="px-4 py-3"><Badge value={v.status} /></td>
                  <td className="px-4 py-3 text-gray-600">{v.zugewiesen_an_name ?? '–'}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {new Date(v.erstellt_am).toLocaleDateString('de-DE')}
                  </td>
                </tr>
              ))}
              {vorgaenge?.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                    Keine Vorgänge gefunden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
