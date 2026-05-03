import React, { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mitarbeiterApi } from '../../api/mitarbeiter'
import type { Mitarbeiter, Abteilung } from '../../types'
import { ABTEILUNG_LABELS } from '../../types'

type SortKey = 'nachname' | 'abteilungen' | 'email' | 'eingetreten_am' | 'aktiv'
type SortDir = 'asc' | 'desc'

interface Filters {
  nachname:    string
  abteilungen: string
  email:       string
  telefon:     string
}

const EMPTY_FILTERS: Filters = { nachname: '', abteilungen: '', email: '', telefon: '' }
const ABTEILUNG_OPTIONS = Object.entries(ABTEILUNG_LABELS) as [Abteilung, string][]

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-gray-300">↕</span>
  return <span className="ml-1 text-primary-600">{dir === 'asc' ? '↑' : '↓'}</span>
}

function abteilungenLabel(abteilungen: Abteilung[]): string {
  return abteilungen.map(a => ABTEILUNG_LABELS[a] ?? a).join(', ')
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface FormData {
  vorname:        string
  nachname:       string
  email:          string
  telefon:        string
  abteilungen:    Abteilung[]
  eingetreten_am: string
  aktiv:          boolean
  passwort:       string
  passwort2:      string
}

const EMPTY_FORM: FormData = {
  vorname: '', nachname: '', email: '', telefon: '',
  abteilungen: [], eingetreten_am: '',
  aktiv: true, passwort: '', passwort2: '',
}

function MitarbeiterModal({ editItem, onClose }: { editItem: Mitarbeiter | null; onClose: () => void }) {
  const qc     = useQueryClient()
  const isEdit = !!editItem

  const [form, setForm] = useState<FormData>(() =>
    editItem
      ? {
          vorname:        editItem.vorname,
          nachname:       editItem.nachname,
          email:          editItem.email,
          telefon:        editItem.telefon,
          abteilungen:    editItem.abteilungen,
          eingetreten_am: editItem.eingetreten_am ?? '',
          aktiv:          editItem.aktiv,
          passwort:       '',
          passwort2:      '',
        }
      : EMPTY_FORM
  )
  const [error, setError] = useState<string | null>(null)

  const set = (key: keyof FormData, value: unknown) =>
    setForm(f => ({ ...f, [key]: value }))

  const toggleAbteilung = (a: Abteilung) =>
    setForm(f => ({
      ...f,
      abteilungen: f.abteilungen.includes(a)
        ? f.abteilungen.filter(x => x !== a)
        : [...f.abteilungen, a],
    }))

  const onError = (err: unknown) => {
    const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
    const msg = data ? Object.values(data).flat().join(' ') : 'Fehler beim Speichern.'
    setError(msg)
  }

  const createMut = useMutation({
    mutationFn: mitarbeiterApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mitarbeiter'] }); onClose() },
    onError,
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof mitarbeiterApi.update>[1] }) =>
      mitarbeiterApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mitarbeiter'] }); onClose() },
    onError,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (form.abteilungen.length === 0) { setError('Bitte mindestens eine Abteilung wählen.'); return }
    if (!isEdit && form.passwort.length < 8) { setError('Passwort muss mindestens 8 Zeichen haben.'); return }
    if (form.passwort && form.passwort !== form.passwort2) { setError('Passwörter stimmen nicht überein.'); return }

    const payload: Partial<Mitarbeiter> & { passwort?: string } = {
      vorname:        form.vorname,
      nachname:       form.nachname,
      email:          form.email,
      telefon:        form.telefon,
      abteilungen:    form.abteilungen,
      eingetreten_am: form.eingetreten_am || null,
      aktiv:          form.aktiv,
    }
    if (form.passwort) payload.passwort = form.passwort

    if (isEdit) updateMut.mutate({ id: editItem.id, data: payload })
    else         createMut.mutate(payload)
  }

  const isBusy  = createMut.isPending || updateMut.isPending
  const inputCls = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400'
  const labelCls = 'block text-xs font-medium text-gray-600 mb-1'

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {/* Name */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Vorname *</label>
              <input className={inputCls} value={form.vorname} onChange={e => set('vorname', e.target.value)} required />
            </div>
            <div>
              <label className={labelCls}>Nachname *</label>
              <input className={inputCls} value={form.nachname} onChange={e => set('nachname', e.target.value)} required />
            </div>
          </div>

          {/* E-Mail (= Login) */}
          <div>
            <label className={labelCls}>E-Mail (= Benutzername) *</label>
            <input
              type="email"
              className={inputCls}
              value={form.email}
              onChange={e => set('email', e.target.value)}
              required
            />
          </div>

          {/* Abteilungen — Checkboxen */}
          <div>
            <label className={labelCls}>Abteilungen * (Mehrfachauswahl möglich)</label>
            <div className="grid grid-cols-2 gap-y-2 gap-x-4 mt-1 p-3 border border-gray-200 rounded-lg bg-gray-50">
              {ABTEILUNG_OPTIONS.map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.abteilungen.includes(value)}
                    onChange={() => toggleAbteilung(value)}
                    className="accent-primary-600"
                  />
                  <span className="text-sm text-gray-700">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Telefon + Eingetreten */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Telefon</label>
              <input className={inputCls} value={form.telefon} onChange={e => set('telefon', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Eingetreten am</label>
              <input type="date" className={inputCls} value={form.eingetreten_am} onChange={e => set('eingetreten_am', e.target.value)} />
            </div>
          </div>

          {/* Aktiv (nur bei Bearbeiten) */}
          {isEdit && (
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.aktiv}
                onChange={e => set('aktiv', e.target.checked)}
                className="accent-primary-600"
              />
              <span className="text-sm text-gray-700">Aktiv</span>
            </label>
          )}

          {/* Passwort */}
          <div className="border-t border-gray-100 pt-3">
            <p className="text-xs text-gray-500 mb-2">
              {isEdit ? 'Passwort (nur ausfüllen wenn ändern)' : 'Login-Passwort *'}
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Passwort {!isEdit && '*'}</label>
                <input
                  type="password"
                  className={inputCls}
                  value={form.passwort}
                  onChange={e => set('passwort', e.target.value)}
                  required={!isEdit}
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
              <div>
                <label className={labelCls}>Wiederholen {!isEdit && '*'}</label>
                <input
                  type="password"
                  className={inputCls}
                  value={form.passwort2}
                  onChange={e => set('passwort2', e.target.value)}
                  required={!isEdit}
                  autoComplete="new-password"
                />
              </div>
            </div>
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={isBusy}
              className="px-5 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {isBusy ? 'Speichern…' : isEdit ? 'Speichern' : 'Anlegen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Hauptseite ───────────────────────────────────────────────────────────────

export function MitarbeiterPage() {
  const qc = useQueryClient()
  const [modal,    setModal]    = useState<'neu' | Mitarbeiter | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [sortKey,  setSortKey]  = useState<SortKey>('nachname')
  const [sortDir,  setSortDir]  = useState<SortDir>('asc')
  const [filters,  setFilters]  = useState<Filters>(EMPTY_FILTERS)

  const { data: mitarbeiter = [], isLoading } = useQuery({
    queryKey: ['mitarbeiter'],
    queryFn:  () => mitarbeiterApi.list(),
  })

  const deleteMut = useMutation({
    mutationFn: mitarbeiterApi.delete,
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['mitarbeiter'] }); setDeleteId(null) },
  })

  const filtered = useMemo(() =>
    mitarbeiter.filter(m =>
      m.vollname.toLowerCase().includes(filters.nachname.toLowerCase()) &&
      abteilungenLabel(m.abteilungen).toLowerCase().includes(filters.abteilungen.toLowerCase()) &&
      m.email.toLowerCase().includes(filters.email.toLowerCase()) &&
      m.telefon.toLowerCase().includes(filters.telefon.toLowerCase()),
    ), [mitarbeiter, filters])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    let cmp = 0
    if      (sortKey === 'nachname')    cmp = a.vollname.localeCompare(b.vollname, 'de')
    else if (sortKey === 'abteilungen') cmp = abteilungenLabel(a.abteilungen).localeCompare(abteilungenLabel(b.abteilungen), 'de')
    else if (sortKey === 'email')       cmp = a.email.localeCompare(b.email, 'de')
    else if (sortKey === 'eingetreten_am') cmp = (a.eingetreten_am ?? '').localeCompare(b.eingetreten_am ?? '')
    else if (sortKey === 'aktiv')       cmp = (b.aktiv ? 1 : 0) - (a.aktiv ? 1 : 0)
    return sortDir === 'asc' ? cmp : -cmp
  }), [filtered, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const setFilter  = (key: keyof Filters, v: string) => setFilters(p => ({ ...p, [key]: v }))
  const hasFilters = Object.values(filters).some(v => v !== '')

  const thCls = 'text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap cursor-pointer select-none hover:bg-gray-100'
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Mitarbeiter</h1>
        <button
          onClick={() => setModal('neu')}
          className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 transition-colors"
        >
          + Neuer Mitarbeiter
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Laden…</p>
      ) : mitarbeiter.length === 0 ? (
        <p className="text-sm text-gray-400">Noch keine Mitarbeiter angelegt.</p>
      ) : (
        <div className="space-y-2">
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className={thCls} onClick={() => handleSort('nachname')}>
                    Name <SortIcon active={sortKey === 'nachname'} dir={sortDir} />
                  </th>
                  <th className={thCls} onClick={() => handleSort('abteilungen')}>
                    Abteilungen <SortIcon active={sortKey === 'abteilungen'} dir={sortDir} />
                  </th>
                  <th className={thCls} onClick={() => handleSort('email')}>
                    E-Mail / Login <SortIcon active={sortKey === 'email'} dir={sortDir} />
                  </th>
                  <th className={thCls}>Telefon</th>
                  <th className={thCls} onClick={() => handleSort('eingetreten_am')}>
                    Eingetreten <SortIcon active={sortKey === 'eingetreten_am'} dir={sortDir} />
                  </th>
                  <th className={thCls} onClick={() => handleSort('aktiv')}>
                    Status <SortIcon active={sortKey === 'aktiv'} dir={sortDir} />
                  </th>
                  <th className="px-3 py-2"></th>
                </tr>
                <tr className="bg-white border-b border-gray-100">
                  <td className="px-3 py-1">{fi('nachname')}</td>
                  <td className="px-3 py-1">{fi('abteilungen')}</td>
                  <td className="px-3 py-1">{fi('email')}</td>
                  <td className="px-3 py-1">{fi('telefon')}</td>
                  <td className="px-3 py-1"></td>
                  <td className="px-3 py-1"></td>
                  <td className="px-3 py-1"></td>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-6 text-center text-sm text-gray-400">
                      Keine Mitarbeiter entsprechen den Filterkriterien.
                    </td>
                  </tr>
                ) : sorted.map(m => (
                  <tr key={m.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-3 py-2.5 font-medium text-gray-800">{m.vollname}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {m.abteilungen.map(a => (
                          <span key={a} className="text-xs px-1.5 py-0.5 rounded bg-primary-50 text-primary-700 border border-primary-100">
                            {ABTEILUNG_LABELS[a] ?? a}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-gray-600">{m.email || '–'}</td>
                    <td className="px-3 py-2.5 text-gray-600">{m.telefon || '–'}</td>
                    <td className="px-3 py-2.5 text-gray-500 text-xs">
                      {m.eingetreten_am ? new Date(m.eingetreten_am).toLocaleDateString('de-DE') : '–'}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        m.aktiv ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {m.aktiv ? 'Aktiv' : 'Inaktiv'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <button onClick={() => setModal(m)} className="text-xs text-primary-600 hover:text-primary-800 mr-3">
                        Bearbeiten
                      </button>
                      <button onClick={() => setDeleteId(m.id)} className="text-xs text-red-400 hover:text-red-600">
                        Löschen
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-gray-500">
              {hasFilters
                ? <><strong>{sorted.length}</strong> von <strong>{mitarbeiter.length}</strong> Mitarbeitern angezeigt</>
                : <><strong>{mitarbeiter.length}</strong> Mitarbeiter gesamt</>
              }
            </p>
            {hasFilters && (
              <button onClick={() => setFilters(EMPTY_FILTERS)} className="text-xs text-primary-600 hover:text-primary-700 underline">
                Filter zurücksetzen
              </button>
            )}
          </div>
        </div>
      )}

      {(modal === 'neu' || (modal && modal !== 'neu')) && (
        <MitarbeiterModal
          editItem={modal !== 'neu' ? modal as Mitarbeiter : null}
          onClose={() => setModal(null)}
        />
      )}

      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full space-y-4">
            <p className="text-sm text-gray-800">
              Mitarbeiter wirklich löschen? Der Login-Account wird ebenfalls entfernt.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeleteId(null)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
                Abbrechen
              </button>
              <button
                onClick={() => deleteMut.mutate(deleteId)}
                disabled={deleteMut.isPending}
                className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMut.isPending ? 'Löschen…' : 'Löschen'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
