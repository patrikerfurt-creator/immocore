import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { handwerkerApi } from '../../api/handwerker'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { fehlerText } from './shared'

export function GewerkeAdmin() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ code: '', bezeichnung: '', sortierung: 0 })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editBezeichnung, setEditBezeichnung] = useState('')
  const [editSortierung, setEditSortierung] = useState(0)

  const { data: gewerke, isLoading, error } = useQuery({
    queryKey: ['gewerke-admin'],
    queryFn: handwerkerApi.gewerkeAdmin.list,
    retry: false,
  })

  const createMutation = useMutation({
    mutationFn: () => handwerkerApi.gewerkeAdmin.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gewerke-admin'] })
      setShowForm(false)
      setForm({ code: '', bezeichnung: '', sortierung: 0 })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { bezeichnung?: string; sortierung?: number; aktiv?: boolean } }) =>
      handwerkerApi.gewerkeAdmin.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gewerke-admin'] })
      setEditingId(null)
    },
  })

  // @ts-expect-error axios error shape
  const istForbidden = error?.response?.status === 403

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Gewerke (Admin)</h1>
        {!istForbidden && (
          <Button onClick={() => setShowForm(v => !v)}>+ Gewerk anlegen</Button>
        )}
      </div>

      {istForbidden && (
        <p className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
          Kein Zugriff — diese Seite ist nur für Administratoren (is_staff) verfügbar.
        </p>
      )}

      {!istForbidden && showForm && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 max-w-md">
          <h2 className="font-semibold text-gray-700 mb-4">Neues Gewerk</h2>
          <div className="flex flex-col gap-3">
            <Input
              label="Code (eindeutig, z.B. sanitaer)"
              value={form.code}
              onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
            />
            <Input
              label="Bezeichnung"
              value={form.bezeichnung}
              onChange={e => setForm(f => ({ ...f, bezeichnung: e.target.value }))}
            />
            <Input
              label="Sortierung"
              type="number"
              value={form.sortierung}
              onChange={e => setForm(f => ({ ...f, sortierung: Number(e.target.value) }))}
            />
            <div className="flex gap-2 mt-2">
              <Button
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending || !form.code || !form.bezeichnung}
              >
                Anlegen
              </Button>
              <Button variant="secondary" onClick={() => setShowForm(false)}>Abbrechen</Button>
            </div>
            {createMutation.isError && (
              <p className="text-red-600 text-sm">{fehlerText(createMutation.error, 'Fehler beim Anlegen.')}</p>
            )}
          </div>
        </div>
      )}

      {isLoading && !istForbidden && <p className="text-gray-400">Laden…</p>}

      {!istForbidden && gewerke && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Code</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Sortierung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {gewerke.map(g => (
                <tr key={g.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{g.code}</td>
                  <td className="px-4 py-3 font-medium text-gray-800">
                    {editingId === g.id ? (
                      <input
                        className="rounded border border-gray-300 px-2 py-1 text-sm"
                        value={editBezeichnung}
                        onChange={e => setEditBezeichnung(e.target.value)}
                      />
                    ) : g.bezeichnung}
                  </td>
                  <td className="px-4 py-3">
                    {editingId === g.id ? (
                      <input
                        type="number"
                        className="w-20 rounded border border-gray-300 px-2 py-1 text-sm"
                        value={editSortierung}
                        onChange={e => setEditSortierung(Number(e.target.value))}
                      />
                    ) : g.sortierung}
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={g.aktiv ? 'aktiv' : 'archiviert'} label={g.aktiv ? 'Aktiv' : 'Deaktiviert'} />
                  </td>
                  <td className="px-4 py-3">
                    {editingId === g.id ? (
                      <div className="flex gap-2">
                        <button
                          className="text-xs text-primary-600 hover:underline disabled:opacity-50"
                          disabled={updateMutation.isPending}
                          onClick={() => updateMutation.mutate({
                            id: g.id, data: { bezeichnung: editBezeichnung, sortierung: editSortierung },
                          })}
                        >
                          Speichern
                        </button>
                        <button className="text-xs text-gray-400 hover:text-gray-600" onClick={() => setEditingId(null)}>
                          Abbrechen
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-3">
                        <button
                          className="text-xs text-primary-600 hover:underline"
                          onClick={() => { setEditingId(g.id); setEditBezeichnung(g.bezeichnung); setEditSortierung(g.sortierung) }}
                        >
                          Bearbeiten
                        </button>
                        <button
                          className="text-xs text-primary-600 hover:underline"
                          onClick={() => updateMutation.mutate({ id: g.id, data: { aktiv: !g.aktiv } })}
                        >
                          {g.aktiv ? 'Deaktivieren' : 'Aktivieren'}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
