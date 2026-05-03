import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { Abrechnungsart } from '../../types'

type FormState = { code: string; bezeichnung: string; aktiv: boolean }

const emptyForm: FormState = { code: '', bezeichnung: '', aktiv: true }

function AbrechnungsartModal({
  objektId,
  editing,
  onClose,
}: {
  objektId: string
  editing: Abrechnungsart | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FormState>(
    editing ? { code: editing.code, bezeichnung: editing.bezeichnung, aktiv: editing.aktiv } : emptyForm
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set(field: keyof FormState, value: string | boolean) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function save() {
    if (!form.code.trim() || !form.bezeichnung.trim()) {
      setError('Code und Bezeichnung sind Pflichtfelder.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (editing) {
        await buchhaltungApi.updateAbrechnungsart(editing.id, form)
      } else {
        await buchhaltungApi.createAbrechnungsart({ ...form, objekt: objektId })
      }
      await qc.invalidateQueries({ queryKey: ['abrechnungsarten', objektId] })
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { code?: string[] } } })?.response?.data?.code?.[0]
      setError(msg ?? 'Speichern fehlgeschlagen.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          {editing ? 'Abrechnungsart bearbeiten' : 'Abrechnungsart hinzufügen'}
        </h2>

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Code (max. 3 Zeichen)</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.code}
              onChange={e => set('code', e.target.value.toUpperCase())}
              maxLength={3}
              placeholder="z.B. 900"
              disabled={!!editing}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Bezeichnung</label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
              value={form.bezeichnung}
              onChange={e => set('bezeichnung', e.target.value)}
              maxLength={100}
              placeholder="z.B. Bewirtschaftung"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="aktiv"
              checked={form.aktiv}
              onChange={e => set('aktiv', e.target.checked)}
              className="h-4 w-4 text-primary-600"
            />
            <label htmlFor="aktiv" className="text-sm text-gray-700">Aktiv</label>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            Abbrechen
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
          >
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function AbrechnungsartenPage() {
  const [searchParams] = useSearchParams()
  const objektId = searchParams.get('objekt')
  const qc = useQueryClient()

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Abrechnungsart | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const { data: list = [], isLoading } = useQuery({
    queryKey: ['abrechnungsarten', objektId],
    queryFn: () => buchhaltungApi.abrechnungsarten(objektId!),
    enabled: !!objektId,
  })

  async function handleDelete(id: string) {
    setDeleting(id)
    try {
      await buchhaltungApi.deleteAbrechnungsart(id)
      await qc.invalidateQueries({ queryKey: ['abrechnungsarten', objektId] })
    } finally {
      setDeleting(null)
    }
  }

  function openAdd() {
    setEditing(null)
    setModalOpen(true)
  }

  function openEdit(a: Abrechnungsart) {
    setEditing(a)
    setModalOpen(true)
  }

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Abrechnungsarten</h1>
        {objektId && (
          <button
            onClick={openAdd}
            className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-700"
          >
            + Hinzufügen
          </button>
        )}
      </div>

      {!objektId && (
        <p className="text-sm text-gray-500">Bitte wähle ein Objekt aus, um die Abrechnungsarten anzuzeigen.</p>
      )}

      {objektId && isLoading && (
        <p className="text-sm text-gray-500">Lade…</p>
      )}

      {objektId && !isLoading && list.length === 0 && (
        <p className="text-sm text-gray-500">Keine Abrechnungsarten vorhanden.</p>
      )}

      {objektId && !isLoading && list.length > 0 && (
        <table className="w-full text-sm border border-gray-200 rounded overflow-hidden">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2 text-left">Code</th>
              <th className="px-4 py-2 text-left">Bezeichnung</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {list.map(a => (
              <tr key={a.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono font-medium">{a.code}</td>
                <td className="px-4 py-2">{a.bezeichnung}</td>
                <td className="px-4 py-2">
                  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                    a.aktiv ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                  }`}>
                    {a.aktiv ? 'Aktiv' : 'Inaktiv'}
                  </span>
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  <button
                    onClick={() => openEdit(a)}
                    className="text-xs text-primary-600 hover:text-primary-800 mr-3"
                  >
                    Bearbeiten
                  </button>
                  <button
                    onClick={() => handleDelete(a.id)}
                    disabled={deleting === a.id}
                    className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                  >
                    {deleting === a.id ? '…' : 'Löschen'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modalOpen && objektId && (
        <AbrechnungsartModal
          objektId={objektId}
          editing={editing}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  )
}
