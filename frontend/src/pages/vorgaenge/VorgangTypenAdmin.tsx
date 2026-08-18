import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { vorgangTypenAdminApi } from '../../api/vorgaenge'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { VorgangPrioritaet } from '../../types'

export function VorgangTypenAdmin() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    code: '', bezeichnung: '', standard_prioritaet: 'normal' as VorgangPrioritaet, sortierung: 0,
  })

  const { data: typen, isLoading, error } = useQuery({
    queryKey: ['vorgang-typen-admin'],
    queryFn: vorgangTypenAdminApi.list,
    retry: false,
  })

  const createMutation = useMutation({
    mutationFn: () => vorgangTypenAdminApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vorgang-typen-admin'] })
      setShowForm(false)
      setForm({ code: '', bezeichnung: '', standard_prioritaet: 'normal', sortierung: 0 })
    },
  })

  const toggleAktivMutation = useMutation({
    mutationFn: ({ id, aktiv }: { id: string; aktiv: boolean }) =>
      vorgangTypenAdminApi.update(id, { aktiv }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang-typen-admin'] }),
  })

  const toggleAntwortVorschlagMutation = useMutation({
    mutationFn: ({ id, antwort_vorschlag_aktiv }: { id: string; antwort_vorschlag_aktiv: boolean }) =>
      vorgangTypenAdminApi.update(id, { antwort_vorschlag_aktiv }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vorgang-typen-admin'] }),
  })

  // @ts-expect-error axios error shape
  const istForbidden = error?.response?.status === 403

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Vorgangs-Typen (Admin)</h1>
        {!istForbidden && (
          <Button onClick={() => setShowForm(v => !v)}>+ Typ anlegen</Button>
        )}
      </div>

      {istForbidden && (
        <p className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
          Kein Zugriff — diese Seite ist nur für Administratoren (is_staff) verfügbar.
        </p>
      )}

      {!istForbidden && showForm && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 max-w-md">
          <h2 className="font-semibold text-gray-700 mb-4">Neuer Vorgangs-Typ</h2>
          <div className="flex flex-col gap-3">
            <Input
              label="Code (eindeutig, z.B. maengelmeldung)"
              value={form.code}
              onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
            />
            <Input
              label="Bezeichnung"
              value={form.bezeichnung}
              onChange={e => setForm(f => ({ ...f, bezeichnung: e.target.value }))}
            />
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Standard-Priorität</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={form.standard_prioritaet}
                onChange={e => setForm(f => ({ ...f, standard_prioritaet: e.target.value as VorgangPrioritaet }))}
              >
                <option value="niedrig">Niedrig</option>
                <option value="normal">Normal</option>
                <option value="hoch">Hoch</option>
              </select>
            </div>
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
              <p className="text-red-600 text-sm">
                {/* @ts-expect-error axios error shape */}
                {JSON.stringify(createMutation.error?.response?.data) ?? 'Fehler beim Anlegen.'}
              </p>
            )}
          </div>
        </div>
      )}

      {isLoading && !istForbidden && <p className="text-gray-400">Laden…</p>}

      {!istForbidden && typen && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Code</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Standard-Priorität</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Sortierung</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">KI-Antwortvorschlag</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {typen.map(t => (
                <tr key={t.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{t.code}</td>
                  <td className="px-4 py-3 font-medium text-gray-800">{t.bezeichnung}</td>
                  <td className="px-4 py-3"><Badge value={t.standard_prioritaet} /></td>
                  <td className="px-4 py-3">{t.sortierung}</td>
                  <td className="px-4 py-3">
                    <Badge value={t.aktiv ? 'aktiv' : 'archiviert'} label={t.aktiv ? 'Aktiv' : 'Deaktiviert'} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="text-xs text-primary-600 hover:underline disabled:opacity-50"
                      disabled={toggleAntwortVorschlagMutation.isPending}
                      onClick={() => toggleAntwortVorschlagMutation.mutate({
                        id: t.id, antwort_vorschlag_aktiv: !t.antwort_vorschlag_aktiv,
                      })}
                    >
                      {t.antwort_vorschlag_aktiv ? 'Aktiv – deaktivieren' : 'Inaktiv – aktivieren'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="text-xs text-primary-600 hover:underline"
                      onClick={() => toggleAktivMutation.mutate({ id: t.id, aktiv: !t.aktiv })}
                    >
                      {t.aktiv ? 'Deaktivieren' : 'Aktivieren'}
                    </button>
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
