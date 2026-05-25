import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { buchhaltungApi } from '../../api/buchhaltung'
import { objekteApi } from '../../api/objekte'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'

const EUR = (v: number | string) =>
  Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

interface Stapel {
  id: string
  bezeichnung: string
  status: string
  erstellt_am: string
  erstellt_von_name: string
  anzahl_buchungen: number
  gesamt_summe: number
}

export function Buchungsjournal() {
  const [searchParams] = useSearchParams()
  const [objektId, setObjektId] = useState(searchParams.get('objekt') ?? '')
  const [statusFilter, setStatusFilter] = useState('')
  const qc = useQueryClient()

  const { data: objekte } = useQuery({ queryKey: ['objekte'], queryFn: objekteApi.list })

  const { data: offeneStapel } = useQuery({
    queryKey: ['buchungsstapel', objektId, 'offen'],
    queryFn: () => buchhaltungApi.stapelListe(objektId ? { objekt: objektId, status: 'offen' } : { status: 'offen' }),
    select: (data: Stapel[]) => data,
  })

  const ausbuchenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.stapelAusbuchen(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buchungsstapel'] })
      qc.invalidateQueries({ queryKey: ['buchungen'] })
    },
  })

  const stornierenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.stornieren(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buchungen'] })
      setStatusFilter('storniert')
    },
    onError: () => alert('Stornierung fehlgeschlagen.'),
  })

  const neuBuchenMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.neuBuchen(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buchungen'] })
      setStatusFilter('entwurf')
    },
    onError: () => alert('Neu buchen fehlgeschlagen.'),
  })

  const { data: buchungen, isLoading } = useQuery({
    queryKey: ['buchungen', objektId, statusFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (statusFilter) params.status = statusFilter
      return buchhaltungApi.buchungen(params)
    },
  })

  async function handleExport() {
    const params: Record<string, string> = {}
    if (objektId) params.objekt = objektId
    const blob = await buchhaltungApi.exportCsv(params)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'buchungsjournal.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Buchungsjournal</h1>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={handleExport}>CSV-Export</Button>
        </div>
      </div>

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
          <option value="entwurf">Entwurf</option>
          <option value="festgeschrieben">Festgeschrieben</option>
          <option value="storniert">Storniert</option>
        </select>
      </div>

      {/* ── Offene Stapel ── */}
      {(offeneStapel ?? []).length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Offene Stapel</h2>
          <div className="bg-white rounded-lg border border-amber-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-amber-50 border-b border-amber-100">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Erstellt am</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Erstellt von</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Bezeichnung</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Buchungen</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Summe</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(offeneStapel ?? []).map((stapel: Stapel) => (
                  <tr key={stapel.id} className="border-t border-amber-50 hover:bg-amber-50">
                    <td className="px-4 py-3 text-gray-600">
                      {new Date(stapel.erstellt_am).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{stapel.erstellt_von_name}</td>
                    <td className="px-4 py-3 text-gray-500">{stapel.bezeichnung || '—'}</td>
                    <td className="px-4 py-3 text-right font-medium">{stapel.anzahl_buchungen}</td>
                    <td className="px-4 py-3 text-right font-medium">{EUR(stapel.gesamt_summe)}</td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        size="sm"
                        onClick={() => ausbuchenMut.mutate(stapel.id)}
                        disabled={ausbuchenMut.isPending || stapel.anzahl_buchungen === 0}
                      >
                        {ausbuchenMut.isPending ? 'Buche…' : 'Ausbuchen'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-gray-400">Laden…</p>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Datum</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Beleg-Nr.</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Soll</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Haben</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Verwendung</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Betrag</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {buchungen?.map(b => (
                <tr key={b.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-600">{new Date(b.buchungsdatum).toLocaleDateString('de-DE')}</td>
                  <td className="px-4 py-3 font-mono text-gray-500">{b.belegnr}</td>
                  <td className="px-4 py-3 font-mono">{b.soll_konto_nr}</td>
                  <td className="px-4 py-3 font-mono">{b.haben_konto_nr}</td>
                  <td className="px-4 py-3 text-gray-600 truncate max-w-xs">{b.verwendungszweck}</td>
                  <td className="px-4 py-3 text-right font-medium">
                    {Number(b.betrag).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                  </td>
                  <td className="px-4 py-3"><Badge value={b.status} /></td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {b.status === 'festgeschrieben' && (
                      <button
                        onClick={() => {
                          if (confirm(`Buchung ${b.belegnr || b.id.slice(0, 8)} stornieren?`))
                            stornierenMut.mutate(b.id)
                        }}
                        disabled={stornierenMut.isPending}
                        className="text-xs text-red-600 hover:underline disabled:opacity-50"
                      >
                        Stornieren
                      </button>
                    )}
                    {b.status === 'storniert' && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => neuBuchenMut.mutate(b.id)}
                        disabled={neuBuchenMut.isPending}
                      >
                        {neuBuchenMut.isPending ? 'Buche…' : 'Neu buchen'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {buchungen?.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                    Keine Buchungen gefunden.
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
