import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { versammlungsortApi } from '../../api/versammlung'
import { apiFehler } from '../../api/fehler'
import type { Versammlungsort } from '../../types'

type FormState = {
  bezeichnung: string
  strasse: string
  plz: string
  ort_text: string
  zusatz: string
  aktiv: boolean
}

function emptyForm(): FormState {
  return { bezeichnung: '', strasse: '', plz: '', ort_text: '', zusatz: '', aktiv: true }
}

function ortToForm(o: Versammlungsort): FormState {
  return {
    bezeichnung: o.bezeichnung,
    strasse: o.strasse,
    plz: o.plz,
    ort_text: o.ort_text,
    zusatz: o.zusatz,
    aktiv: o.aktiv,
  }
}

function VersammlungsortModal({
  ort,
  onClose,
}: {
  ort: Versammlungsort | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const isEdit = ort !== null
  const [form, setForm] = useState<FormState>(ort ? ortToForm(ort) : emptyForm())
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(f => ({ ...f, [key]: value }))
  }

  const mutation = useMutation({
    mutationFn: () => {
      if (isEdit) return versammlungsortApi.update(ort!.id, form)
      return versammlungsortApi.create(form)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['versammlungsorte'] })
      onClose()
    },
    onError: (e: unknown) => setError(apiFehler(e, 'Fehler beim Speichern')),
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">
            {isEdit ? 'Versammlungsort bearbeiten' : 'Neuer Versammlungsort'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
        </div>

        <form
          onSubmit={e => { e.preventDefault(); setError(null); mutation.mutate() }}
          className="px-6 py-4 space-y-4"
        >
          <div>
            <label className="block text-xs text-gray-500 mb-1">Bezeichnung *</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.bezeichnung}
              onChange={e => set('bezeichnung', e.target.value)}
              maxLength={200}
              required
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Straße</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.strasse}
              onChange={e => set('strasse', e.target.value)}
              maxLength={255}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">PLZ</label>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.plz}
                onChange={e => set('plz', e.target.value)}
                maxLength={10}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Ort</label>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                value={form.ort_text}
                onChange={e => set('ort_text', e.target.value)}
                maxLength={120}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Zusatz (Raum, Etage, Zugang)</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.zusatz}
              onChange={e => set('zusatz', e.target.value)}
              maxLength={255}
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.aktiv}
              onChange={e => set('aktiv', e.target.checked)}
              className="rounded"
            />
            Aktiv
          </label>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-3 pt-2 border-t border-gray-100">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Speichern…' : 'Speichern'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function VersammlungsortePage() {
  const [modalOrt, setModalOrt] = useState<Versammlungsort | 'new' | null>(null)

  const { data: orte = [], isLoading } = useQuery({
    queryKey: ['versammlungsorte'],
    queryFn: versammlungsortApi.list,
  })

  if (isLoading) return <p className="text-gray-400">Laden…</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Versammlungsorte</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">{orte.length} Orte</span>
          <button
            onClick={() => setModalOrt('new')}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-700"
          >
            + Neuer Ort
          </button>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Katalog zur Vorbelegung des Versammlungsorts beim Anlegen/Ändern einer
        Eigentümerversammlung. Das Textfeld „Ort" der Versammlung bleibt davon
        unberührt und ist der maßgebliche, änderbare Wert (GoBD-Snapshot zum
        Versammlungszeitpunkt) — nicht löschen, sondern bei Nichtgebrauch
        deaktivieren.
      </p>

      {orte.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
          <p className="text-gray-500">Noch keine Versammlungsorte angelegt.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Straße</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">PLZ / Ort</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Zusatz</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">Aktiv</th>
              </tr>
            </thead>
            <tbody>
              {orte.map(o => (
                <tr
                  key={o.id}
                  onClick={() => setModalOrt(o)}
                  className={`border-b border-gray-50 hover:bg-primary-50 cursor-pointer transition-colors ${!o.aktiv ? 'opacity-50' : ''}`}
                >
                  <td className="px-4 py-2.5 text-gray-800">{o.bezeichnung}</td>
                  <td className="px-4 py-2.5 text-gray-600">{o.strasse || '–'}</td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {o.plz || o.ort_text ? `${o.plz} ${o.ort_text}`.trim() : '–'}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">{o.zusatz || '–'}</td>
                  <td className="px-4 py-2.5 text-center">
                    {o.aktiv
                      ? <span className="text-green-600 text-xs font-medium">Aktiv</span>
                      : <span className="text-gray-400 text-xs">Inaktiv</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOrt && (
        <VersammlungsortModal
          ort={modalOrt === 'new' ? null : modalOrt}
          onClose={() => setModalOrt(null)}
        />
      )}
    </div>
  )
}
