import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { rechnungenApi } from '../../api/rechnungen'
import type { RechnungList } from '../../types'
import { Ampelpunkt } from './Ampel'

type Filter = 'offen' | 'mir' | 'alle'

const STATUS_LABEL: Record<string, string> = {
  importiert: 'Eingegangen',
  erkannt: 'Eingegangen (erkannt)',
  pruefung_match: 'Eingegangen (Prüfung)',
  nicht_erkannt: 'Eingegangen (unklar)',
  erfasst: 'Erfasst',
  in_freigabe: 'In Freigabe',
}

function skontoBadge(r: RechnungList): string | null {
  if (!r.skonto_faellig_bis || r.skonto_genutzt) return null
  const frist = new Date(r.skonto_faellig_bis)
  const tage = Math.ceil((frist.getTime() - Date.now()) / 86_400_000)
  if (tage < 0) return null
  const d = frist.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  return tage <= 5 ? `Skonto bis ${d} (${tage} T.)` : `Skonto bis ${d}`
}

export default function BuchhaltungsInbox() {
  const [filter, setFilter] = useState<Filter>('offen')
  const [rows, setRows] = useState<RechnungList[]>([])
  const [loading, setLoading] = useState(true)
  const [fehler, setFehler] = useState<string | null>(null)
  const navigate = useNavigate()

  const laden = useCallback(() => {
    setLoading(true)
    rechnungenApi.inbox(filter)
      .then(setRows)
      .catch(() => setFehler('Inbox konnte nicht geladen werden.'))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => { laden() }, [laden])

  const freigeben = async (r: RechnungList) => {
    try {
      await rechnungenApi.freigeben(r.id)
      laden()
    } catch (e) {
      const msg = (e as { response?: { data?: { error?: string } } }).response?.data?.error
      alert(msg ?? 'Freigabe nicht möglich.')
    }
  }

  const ablehnen = async (r: RechnungList) => {
    const grund = window.prompt('Begründung der Ablehnung:')
    if (grund == null) return
    await rechnungenApi.ablehnen(r.id, grund)
    laden()
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-800">Rechnungseingang — Inbox</h1>
        <button
          onClick={() => navigate('/rechnungen/erfassen')}
          className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
        >
          + Rechnung erfassen
        </button>
      </div>

      <div className="flex gap-2 mb-4">
        {(['offen', 'mir', 'alle'] as Filter[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 text-sm rounded ${filter === f ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-700'}`}
          >
            {f === 'offen' ? 'Offen' : f === 'mir' ? 'Mir zugewiesen' : 'Alle'}
          </button>
        ))}
      </div>

      {fehler && <div className="mb-3 text-sm text-red-600">{fehler}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm">Lädt…</div>
      ) : rows.length === 0 ? (
        <div className="text-gray-500 text-sm">Keine offenen Rechnungen.</div>
      ) : (
        <div className="overflow-x-auto border rounded">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-3 py-2 text-left">Ampel</th>
                <th className="px-3 py-2 text-left">Eingang</th>
                <th className="px-3 py-2 text-left">Kreditor</th>
                <th className="px-3 py-2 text-left">Objekt</th>
                <th className="px-3 py-2 text-right">Betrag</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Erfasst von</th>
                <th className="px-3 py-2 text-left">Skonto</th>
                <th className="px-3 py-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const badge = skontoBadge(r)
                return (
                  <tr key={r.id} className="border-t hover:bg-gray-50">
                    <td className="px-3 py-2"><Ampelpunkt ampel={r.erkennung_ampel} /></td>
                    <td className="px-3 py-2 text-gray-600">
                      {new Date(r.erstellt_am).toLocaleDateString('de-DE')}
                    </td>
                    <td className="px-3 py-2">{r.kreditor_name || r.lieferant_name || '—'}</td>
                    <td className="px-3 py-2 text-gray-600">{r.objekt_bezeichnung ?? '—'}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {r.betrag_brutto ? `${Number(r.betrag_brutto).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €` : '—'}
                    </td>
                    <td className="px-3 py-2">{STATUS_LABEL[r.status] ?? r.status}</td>
                    <td className="px-3 py-2 text-gray-600">{r.erfasst_von_name ?? '—'}</td>
                    <td className="px-3 py-2">
                      {badge && (
                        <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-800">{badge}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <button onClick={() => navigate(`/rechnungen/erfassen/${r.id}`)}
                              className="text-blue-600 hover:underline mr-3">Öffnen</button>
                      {r.status === 'in_freigabe' && (
                        <button onClick={() => freigeben(r)} className="text-green-700 hover:underline mr-3">Freigeben</button>
                      )}
                      <button onClick={() => ablehnen(r)} className="text-red-600 hover:underline">Ablehnen</button>
                    </td>
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
