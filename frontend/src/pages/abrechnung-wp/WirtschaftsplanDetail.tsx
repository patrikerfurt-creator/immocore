import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi, type Wirtschaftsplan, type WirtschaftsplanPosition } from '../../api/wirtschaftsplan'

const STATUS_LABEL: Record<string, string> = {
  entwurf:     'Entwurf',
  beschlossen: 'Beschlossen',
  aktiv:       'Aktiv',
  aufgehoben:  'Aufgehoben',
}
const STATUS_COLOR: Record<string, string> = {
  entwurf:     'bg-gray-100 text-gray-600',
  beschlossen: 'bg-blue-100 text-blue-700',
  aktiv:       'bg-green-100 text-green-700',
  aufgehoben:  'bg-red-100 text-red-500',
}

function fmtDate(iso: string | null) {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
function fmtEur(val: string | null) {
  if (!val) return '–'
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
}
function diffStatus(pos: WirtschaftsplanPosition) {
  const diff = Math.abs(parseFloat(pos.differenz))
  if (diff <= 0.10) return { icon: '🟢', label: 'ok' }
  if (diff <= 1.00) return { icon: '🟡', label: `Δ ${diff.toFixed(2)} €` }
  return { icon: '🔴', label: `Δ ${diff.toFixed(2)} €` }
}

export function WirtschaftsplanDetail() {
  const { wpId } = useParams<{ wpId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: wp, isLoading } = useQuery({
    queryKey: ['wirtschaftsplan', wpId],
    queryFn: () => wirtschaftsplanApi.get(wpId!),
    enabled: !!wpId,
  })

  const [pdfLoading, setPdfLoading] = useState<string | null>(null)

  const handlePdfGesamt = async () => {
    if (!wp) return
    setPdfLoading('gesamt')
    try {
      await wirtschaftsplanApi.downloadGesamtPdf(wp.id, `Wirtschaftsplan_WJ${wp.wj_jahr}.pdf`)
    } finally {
      setPdfLoading(null)
    }
  }

  const handlePdfBulk = async () => {
    if (!wp) return
    setPdfLoading('bulk')
    try {
      await wirtschaftsplanApi.downloadBulkZip(wp.id, `Einzelwirtschaftsplaene_WJ${wp.wj_jahr}.zip`)
    } finally {
      setPdfLoading(null)
    }
  }

  const korrekturbeschlussMut = useMutation({
    mutationFn: () => wirtschaftsplanApi.korrekturbeschluss(wpId!),
    onSuccess: (neuerWp: Wirtschaftsplan) => {
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
      navigate(`/abrechnung-wp/wirtschaftsplan/${neuerWp.id}/wizard`)
    },
  })

  if (isLoading) return <div className="p-6 text-sm text-gray-400">Laden…</div>
  if (!wp) return <div className="p-6 text-sm text-red-500">Nicht gefunden.</div>

  const isEditable = wp.status === 'entwurf'

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-gray-900">Wirtschaftsplan WJ {wp.wj_jahr}</h1>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[wp.status]}`}>
              {STATUS_LABEL[wp.status]}
            </span>
          </div>
          <p className="text-sm text-gray-500">{wp.objekt_bezeichnung}</p>
          <p className="text-xs text-gray-400 mt-1">Wirkung ab {fmtDate(wp.wirkung_ab)}</p>
        </div>
        <div className="flex gap-2">
          {isEditable && (
            <button
              onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/${wp.id}/wizard`)}
              className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700"
            >
              Bearbeiten
            </button>
          )}
          {(wp.status === 'beschlossen' || wp.status === 'aktiv') && (
            <button
              onClick={() => korrekturbeschlussMut.mutate()}
              disabled={korrekturbeschlussMut.isPending}
              className="border border-amber-400 text-amber-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-50"
            >
              Korrekturbeschluss erstellen
            </button>
          )}
          {(wp.positionen?.length ?? 0) > 0 && (
            <>
              <button
                onClick={handlePdfGesamt}
                disabled={pdfLoading !== null}
                className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
              >
                {pdfLoading === 'gesamt' ? '…' : 'Gesamt-PDF'}
              </button>
              <button
                onClick={handlePdfBulk}
                disabled={pdfLoading !== null}
                className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
              >
                {pdfLoading === 'bulk' ? '…' : 'Einzelpläne (ZIP)'}
              </button>
            </>
          )}
        </div>
      </div>

      {(wp.status === 'beschlossen' || wp.status === 'aktiv') && (
        <div className="mb-4 rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-700">
          Dieser Wirtschaftsplan ist beschlossen. Für Änderungen einen Korrekturbeschluss erstellen.
        </div>
      )}

      {/* Zusammenfassung */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Gesamtsumme</p>
          <p className="text-xl font-bold text-gray-900">{fmtEur(wp.gesamtsumme)}</p>
        </div>
        <div className="rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Hausgeld (lfd.)</p>
          <p className="text-xl font-bold text-primary-700">{fmtEur(wp.gesamtsumme_hausgeld)}</p>
        </div>
        <div className="rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Beschluss-Datum</p>
          <p className="text-lg font-semibold text-gray-800">{fmtDate(wp.beschluss_datum)}</p>
          {wp.beschluss_tagesordnungspunkt && (
            <p className="text-xs text-gray-400">{wp.beschluss_tagesordnungspunkt}</p>
          )}
        </div>
      </div>

      {/* Positionen */}
      <h2 className="text-base font-semibold text-gray-800 mb-3">Positionen ({wp.positionen?.length ?? 0})</h2>
      {(!wp.positionen || wp.positionen.length === 0) ? (
        <p className="text-sm text-gray-400">Keine Positionen erfasst.</p>
      ) : (
        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-20">Konto</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600">Bezeichnung</th>
                <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-12">VS</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-28">Betrag</th>
                <th className="text-right px-4 py-2.5 font-medium text-gray-600 w-28">Monatlich</th>
                <th className="text-center px-4 py-2.5 font-medium text-gray-600 w-20">Status</th>
              </tr>
            </thead>
            <tbody>
              {wp.positionen.map((pos: WirtschaftsplanPosition) => {
                const ds = diffStatus(pos)
                const monatlich = parseFloat(pos.betrag) / 12
                return (
                  <tr key={pos.id} className="border-t border-gray-100">
                    <td className="px-4 py-2.5 font-mono text-gray-500">{pos.kontonummer}</td>
                    <td className="px-4 py-2.5 text-gray-700">{pos.kontoname}</td>
                    <td className="px-4 py-2.5 text-gray-400 font-mono">{pos.vs_code}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{fmtEur(pos.betrag)}</td>
                    <td className="px-4 py-2.5 text-right text-gray-500">
                      {monatlich.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                    </td>
                    <td className="px-4 py-2.5 text-center text-xs">
                      <span title={ds.label}>{ds.icon}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="bg-gray-50 border-t border-gray-200">
              <tr>
                <td colSpan={3} className="px-4 py-2.5 font-medium text-gray-700">Gesamt</td>
                <td className="px-4 py-2.5 text-right font-bold text-gray-900">{fmtEur(wp.gesamtsumme)}</td>
                <td className="px-4 py-2.5 text-right font-medium text-gray-700">
                  {(parseFloat(wp.gesamtsumme) / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}
