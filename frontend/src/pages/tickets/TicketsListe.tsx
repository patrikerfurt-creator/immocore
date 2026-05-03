import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ticketsApi } from '../../api/tickets'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { TicketTyp, TicketPrioritaet } from '../../types'

export function TicketsListe() {
  const [searchParams] = useSearchParams()
  const [objektId, setObjektId] = useState(searchParams.get('objekt') ?? '')
  const [statusFilter, setStatusFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    objekt: '',
    titel: '',
    beschreibung: '',
    ticket_typ: 'anfrage' as TicketTyp,
    prioritaet: 'mittel' as TicketPrioritaet,
  })
  const queryClient = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })
  const { data: tickets, isLoading } = useQuery({
    queryKey: ['tickets', objektId, statusFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (statusFilter) params.status = statusFilter
      return ticketsApi.list(params)
    },
  })

  const createMutation = useMutation({
    mutationFn: () => ticketsApi.create(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      setShowForm(false)
      setForm({ objekt: '', titel: '', beschreibung: '', ticket_typ: 'anfrage', prioritaet: 'mittel' })
    },
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      ticketsApi.statusAendern(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tickets'] }),
  })

  const nextStatus: Record<string, string> = {
    offen: 'in_bearbeitung',
    in_bearbeitung: 'erledigt',
    erledigt: 'geschlossen',
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tickets</h1>
        <Button onClick={() => setShowForm(!showForm)}>+ Ticket erstellen</Button>
      </div>

      {showForm && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 max-w-lg">
          <h2 className="font-semibold text-gray-700 mb-4">Neues Ticket</h2>
          <div className="flex flex-col gap-3">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Objekt</label>
              <select
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={form.objekt}
                onChange={e => setForm(f => ({ ...f, objekt: e.target.value }))}
              >
                <option value="">Objekt wählen…</option>
                {objekte?.map(o => (
                  <option key={o.id} value={o.id}>{o.objektnummer} – {o.bezeichnung}</option>
                ))}
              </select>
            </div>
            <Input
              label="Titel"
              value={form.titel}
              onChange={e => setForm(f => ({ ...f, titel: e.target.value }))}
            />
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Beschreibung</label>
              <textarea
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm h-20 resize-none"
                value={form.beschreibung}
                onChange={e => setForm(f => ({ ...f, beschreibung: e.target.value }))}
              />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-sm font-medium text-gray-700 block mb-1">Typ</label>
                <select
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={form.ticket_typ}
                  onChange={e => setForm(f => ({ ...f, ticket_typ: e.target.value as TicketTyp }))}
                >
                  <option value="maengelmeldung">Mängelmedlung</option>
                  <option value="anfrage">Anfrage</option>
                  <option value="aufgabe">Aufgabe</option>
                  <option value="sonstiges">Sonstiges</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="text-sm font-medium text-gray-700 block mb-1">Priorität</label>
                <select
                  className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={form.prioritaet}
                  onChange={e => setForm(f => ({ ...f, prioritaet: e.target.value as TicketPrioritaet }))}
                >
                  <option value="niedrig">Niedrig</option>
                  <option value="mittel">Mittel</option>
                  <option value="hoch">Hoch</option>
                  <option value="kritisch">Kritisch</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2 mt-2">
              <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                Erstellen
              </Button>
              <Button variant="secondary" onClick={() => setShowForm(false)}>Abbrechen</Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-3 mb-4">
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          value={objektId}
          onChange={e => setObjektId(e.target.value)}
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
          <option value="offen">Offen</option>
          <option value="in_bearbeitung">In Bearbeitung</option>
          <option value="erledigt">Erledigt</option>
          <option value="geschlossen">Geschlossen</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Titel</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Typ</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Priorität</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Erstellt am</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {tickets?.map(t => (
                <tr key={t.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">{t.titel}</td>
                  <td className="px-4 py-3"><Badge value={t.ticket_typ} label={t.ticket_typ} /></td>
                  <td className="px-4 py-3"><Badge value={t.prioritaet} /></td>
                  <td className="px-4 py-3"><Badge value={t.status} /></td>
                  <td className="px-4 py-3 text-gray-600">
                    {new Date(t.erstellt_am).toLocaleDateString('de-DE')}
                  </td>
                  <td className="px-4 py-3">
                    {nextStatus[t.status] && (
                      <button
                        onClick={() => statusMutation.mutate({ id: t.id, status: nextStatus[t.status] })}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        → {nextStatus[t.status].replace('_', ' ')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {tickets?.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                    Keine Tickets gefunden.
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
