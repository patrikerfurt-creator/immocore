import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { wkzApi, type WKZVorlage } from '../../../api/wkz'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { useObjektStore } from '../../../stores/objekt'

const STATUS_FARBE: Record<string, 'green' | 'yellow' | 'gray' | 'blue'> = {
  aktiv: 'green',
  pausiert: 'yellow',
  beendet: 'gray',
  entwurf: 'blue',
}

const STATUS_TEXT: Record<string, string> = {
  aktiv: 'Aktiv',
  pausiert: 'Pausiert',
  beendet: 'Beendet',
  entwurf: 'Entwurf',
}

const RHYTHMUS_TEXT: Record<string, string> = {
  monatlich: 'Monatlich',
  zweimonatlich: 'Zweimonatlich',
  quartalsweise: 'Quartalsweise',
  halbjaehrlich: 'Halbjährlich',
  jaehrlich: 'Jährlich',
  frei: 'Frei',
}

const EUR = (v: string | number | null) =>
  v !== null ? Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }) : '–'

const DATUM = (s: string | null) =>
  s ? new Date(s).toLocaleDateString('de-DE') : '–'

// ---------------------------------------------------------------------------
// Pausieren-Modal
// ---------------------------------------------------------------------------

function PausierenModal({
  vorlage,
  onClose,
  onSuccess,
}: {
  vorlage: WKZVorlage
  onClose: () => void
  onSuccess: () => void
}) {
  const [grund, setGrund] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => wkzApi.vorlagePausieren(vorlage.id, grund),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wkz-vorlagen'] })
      onSuccess()
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold mb-4">Vorlage pausieren</h2>
        <p className="text-sm text-gray-600 mb-4">
          <strong>{vorlage.bezeichnung}</strong> — keine weiteren OPs werden erzeugt.
        </p>
        <label className="block text-sm font-medium text-gray-700 mb-1">Grund</label>
        <textarea
          value={grund}
          onChange={e => setGrund(e.target.value)}
          rows={3}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          placeholder="Warum wird die Vorlage pausiert?"
        />
        {mutation.isError && (
          <p className="text-red-600 text-sm mt-2">
            {(mutation.error as Error)?.message ?? 'Fehler'}
          </p>
        )}
        <div className="flex justify-end gap-3 mt-4">
          <Button variant="secondary" onClick={onClose}>Abbrechen</Button>
          <Button
            variant="primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            Pausieren
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export default function VorlagenListe() {
  const { aktuellesObjekt } = useObjektStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('')
  const [pausierenVorlage, setPausierenVorlage] = useState<WKZVorlage | null>(null)

  const { data: vorlagen = [], isLoading, error } = useQuery({
    queryKey: ['wkz-vorlagen', aktuellesObjekt?.id, statusFilter],
    queryFn: () =>
      wkzApi.vorlagenJeObjekt(
        aktuellesObjekt!.id,
        statusFilter ? { status: statusFilter } : undefined,
      ),
    enabled: !!aktuellesObjekt,
  })

  const einreichenMutation = useMutation({
    mutationFn: (id: string) => wkzApi.vorlageEinreichen(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wkz-vorlagen'] }),
  })

  const reaktivierenMutation = useMutation({
    mutationFn: (id: string) => wkzApi.vorlageReaktivieren(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wkz-vorlagen'] }),
  })

  if (!aktuellesObjekt) {
    return <p className="text-gray-500 p-4">Bitte ein Objekt auswählen.</p>
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Wiederkehrende Buchungen</h1>
        <Button variant="primary" onClick={() => navigate('neu')}>
          + Neue Vorlage
        </Button>
      </div>

      {/* Filter */}
      <div className="flex gap-3 flex-wrap">
        {['', 'aktiv', 'entwurf', 'pausiert', 'beendet'].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-sm border ${
              statusFilter === s
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
            }`}
          >
            {s === '' ? 'Alle' : STATUS_TEXT[s]}
          </button>
        ))}
      </div>

      {/* Tabelle */}
      {isLoading ? (
        <p className="text-gray-400">Lade Vorlagen…</p>
      ) : error ? (
        <p className="text-red-600">Fehler beim Laden.</p>
      ) : vorlagen.length === 0 ? (
        <p className="text-gray-400">Keine Vorlagen gefunden.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Bezeichnung</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Kreditor</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Rhythmus</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Betrag</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Jahresbetrag</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Geltung</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Aktionen</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {vorlagen.map(v => (
                <tr key={v.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to={v.id}
                      className="text-blue-600 hover:underline font-medium"
                    >
                      {v.bezeichnung}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{v.kreditor_name}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {RHYTHMUS_TEXT[v.rhythmus] ?? v.rhythmus}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {EUR(v.betrag_gesamt)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-gray-500">
                    {EUR(v.jahresbetrag)}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {DATUM(v.gueltig_ab)}
                    {v.gueltig_bis ? ` – ${DATUM(v.gueltig_bis)}` : ' – unbefristet'}
                  </td>
                  <td className="px-4 py-3">
                    <Badge color={STATUS_FARBE[v.status] ?? 'gray'}>
                      {STATUS_TEXT[v.status] ?? v.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                    {v.status === 'entwurf' && (
                      <button
                        onClick={() => einreichenMutation.mutate(v.id)}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        Einreichen
                      </button>
                    )}
                    {v.status === 'aktiv' && (
                      <button
                        onClick={() => setPausierenVorlage(v)}
                        className="text-xs text-yellow-600 hover:underline"
                      >
                        Pausieren
                      </button>
                    )}
                    {v.status === 'pausiert' && (
                      <button
                        onClick={() => reaktivierenMutation.mutate(v.id)}
                        className="text-xs text-green-600 hover:underline"
                      >
                        Reaktivieren
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pausierenVorlage && (
        <PausierenModal
          vorlage={pausierenVorlage}
          onClose={() => setPausierenVorlage(null)}
          onSuccess={() => setPausierenVorlage(null)}
        />
      )}
    </div>
  )
}
