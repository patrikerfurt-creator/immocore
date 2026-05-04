import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { rechnungenApi } from '../../api/rechnungen'
import { useAuthStore } from '../../stores/auth'
import type { RechnungList } from '../../types'

const EUR = (v: string | number | null) =>
  v == null ? '—' : Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
const DATUM = (s: string | null) => s ? new Date(s).toLocaleDateString('de-DE') : '—'

export default function FrontofficeInbox() {
  const navigate = useNavigate()
  const { istFrontoffice } = useAuthStore()

  const { data: rechnungen, isLoading } = useQuery({
    queryKey: ['frontoffice-inbox'],
    queryFn: () => rechnungenApi.list({ routing_ziel: 'frontoffice', zugewiesen_an: 'null', ordering: 'erstellt_am' }),
    refetchInterval: 30_000,
  })

  if (!istFrontoffice) {
    return (
      <div className="p-8 text-center text-gray-500">
        Diese Seite ist nur für Frontoffice-Mitarbeiter zugänglich.
      </div>
    )
  }

  const handleOeffnen = async (r: RechnungList) => {
    try {
      await rechnungenApi.lockSetzen(r.id)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { locked_by?: string } } })?.response?.data?.locked_by
      if (msg) {
        alert(`Diese Rechnung wird gerade von ${msg} bearbeitet.`)
        return
      }
    }
    navigate(`/rechnungen/${r.id}/prueffall`)
  }

  const liste = (rechnungen ?? []) as (RechnungList & { lock_user?: string | null })[]

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Frontoffice-Inbox</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Rechnungen ohne erkanntes Objekt — Stufe 3 (unbekannt)
        </p>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Lade…</div>
      ) : liste.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-8 text-center text-green-700 font-medium">
          Inbox leer — keine offenen Rechnungen
        </div>
      ) : (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Eingang</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Stufe</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Erkannter Kreditor</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Leistungstext</th>
                <th className="text-right px-4 py-3 text-gray-500 font-medium w-32">Betrag</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium w-36">Status</th>
                <th className="px-4 py-3 w-8" />
              </tr>
            </thead>
            <tbody>
              {liste.map(r => {
                const gesperrt = !!r.lock_user
                return (
                  <tr
                    key={r.id}
                    onClick={() => !gesperrt && handleOeffnen(r)}
                    className={`border-t ${gesperrt ? 'opacity-60 cursor-not-allowed bg-gray-50' : 'hover:bg-orange-50 cursor-pointer'}`}
                  >
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{DATUM(r.erstellt_am)}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700">
                        {r.erkennungs_stufe === '3' ? 'Stufe 3 — Frontoffice' : 'Stufe 3'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {r.kreditor_name
                        ? <span className="text-gray-800 font-medium">{r.kreditor_name}</span>
                        : <span className="text-gray-400 text-xs">nicht erkannt</span>
                      }
                      {r.dateiname && (
                        <div className="text-xs text-gray-400 truncate max-w-[160px]">{r.dateiname}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 truncate max-w-[200px]">
                      {r.leistungstext || '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">
                      {EUR(r.betrag_brutto)}
                    </td>
                    <td className="px-4 py-3">
                      {gesperrt ? (
                        <span className="text-xs text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full whitespace-nowrap">
                          🔒 {r.lock_user}
                        </span>
                      ) : (
                        <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded-full">frei</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-300 text-lg">{gesperrt ? '' : '›'}</td>
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
