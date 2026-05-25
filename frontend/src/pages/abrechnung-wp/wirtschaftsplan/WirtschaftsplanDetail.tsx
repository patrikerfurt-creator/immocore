import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi } from '../../../api/wirtschaftsplan'

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

const STATUS_LABEL: Record<string, string> = {
  entwurf: 'Entwurf',
  beschlossen: 'Beschlossen',
  aktiv: 'Aktiv',
  aufgehoben: 'Aufgehoben',
}
const STATUS_COLOR: Record<string, string> = {
  entwurf: 'bg-yellow-100 text-yellow-800',
  beschlossen: 'bg-blue-100 text-blue-800',
  aktiv: 'bg-green-100 text-green-800',
  aufgehoben: 'bg-gray-100 text-gray-500',
}

function fmt(v: string | number) {
  return Number(v).toLocaleString('de-DE', { minimumFractionDigits: 2 })
}

export function WirtschaftsplanDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: wp, isLoading } = useQuery({
    queryKey: ['wp-detail', id],
    queryFn: () => wirtschaftsplanApi.get(id!),
    enabled: !!id,
  })

  const [beschlussOffen, setBeschlussOffen] = useState(false)
  const [beschlussDatum, setBeschlussDatum] = useState(new Date().toISOString().split('T')[0])
  const [top, setTop] = useState('')
  const [bemerkung, setBemerkung] = useState('')
  const [beschlussError, setBeschlussError] = useState<string | null>(null)

  const [pdfLoading, setPdfLoading] = useState<string | null>(null)

  const handlePdfGesamt = async () => {
    setPdfLoading('gesamt')
    try {
      const blob = await wirtschaftsplanApi.pdfGesamt(id!)
      downloadBlob(blob, `WP_${wp?.wirtschaftsjahr_jahr}.pdf`)
    } finally {
      setPdfLoading(null)
    }
  }

  const handlePdfBulk = async () => {
    setPdfLoading('bulk')
    try {
      const blob = await wirtschaftsplanApi.pdfEinzeln(id!, { bulk: true })
      downloadBlob(blob, `Einzelwirtschaftsplaene_${wp?.wirtschaftsjahr_jahr}.zip`)
    } finally {
      setPdfLoading(null)
    }
  }

  const beschlussMut = useMutation({
    mutationFn: () => wirtschaftsplanApi.beschluss(id!, { beschluss_datum: beschlussDatum, top, bemerkung }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wp-detail', id] })
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
      setBeschlussOffen(false)
    },
    onError: (e: any) => setBeschlussError(e?.response?.data?.detail ?? 'Fehler beim Beschluss'),
  })

  const korrekturbeschlussMut = useMutation({
    mutationFn: () => wirtschaftsplanApi.korrekturbeschluss(id!),
    onSuccess: (neu) => {
      qc.invalidateQueries({ queryKey: ['wirtschaftsplaene'] })
      navigate(`/abrechnung-wp/wirtschaftsplan/${neu.id}/wizard?wp=${neu.id}`)
    },
  })

  if (isLoading) return <p className="text-sm text-gray-400">Lade...</p>
  if (!wp) return <p className="text-sm text-red-600">Nicht gefunden.</p>

  const istBearbeitbar = wp.status === 'entwurf'
  const istBeschlossen = wp.status === 'beschlossen' || wp.status === 'aktiv'

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            ←
          </button>
          <h1 className="text-xl font-semibold text-gray-800">
            Wirtschaftsplan {wp.wirtschaftsjahr_jahr}
          </h1>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[wp.status]}`}>
            {STATUS_LABEL[wp.status]}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handlePdfGesamt}
            disabled={pdfLoading === 'gesamt'}
            className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50 disabled:opacity-50"
          >
            {pdfLoading === 'gesamt' ? '...' : '📄 Gesamt-PDF'}
          </button>
          <button
            onClick={handlePdfBulk}
            disabled={pdfLoading === 'bulk'}
            className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50 disabled:opacity-50"
          >
            {pdfLoading === 'bulk' ? '...' : '📦 Einzelpläne (ZIP)'}
          </button>
          {istBearbeitbar && (
            <button
              onClick={() => navigate(`/abrechnung-wp/wirtschaftsplan/wizard?objekt=${wp.objekt_id}&wp=${wp.id}`)}
              className="px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
            >
              Bearbeiten (Wizard)
            </button>
          )}
          {istBeschlossen && (
            <button
              onClick={() => korrekturbeschlussMut.mutate()}
              disabled={korrekturbeschlussMut.isPending}
              className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50 disabled:opacity-50"
            >
              Korrekturbeschluss anlegen
            </button>
          )}
        </div>
      </div>

      {istBeschlossen && (
        <div className="bg-blue-50 border border-blue-200 text-blue-800 text-sm px-4 py-3 rounded">
          Dieser Wirtschaftsplan ist {STATUS_LABEL[wp.status].toLowerCase()}. Für Änderungen einen Korrekturbeschluss anlegen.
        </div>
      )}

      {/* Stammdaten */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-500">Objekt</span>
          <p className="font-medium">{wp.objekt_bezeichnung}</p>
        </div>
        <div>
          <span className="text-gray-500">Wirtschaftsjahr</span>
          <p className="font-medium">{wp.wirtschaftsjahr_jahr}</p>
        </div>
        <div>
          <span className="text-gray-500">Wirkung ab</span>
          <p className="font-medium">{wp.wirkung_ab}</p>
        </div>
        {wp.beschluss_datum && (
          <div>
            <span className="text-gray-500">Beschluss-Datum</span>
            <p className="font-medium">{wp.beschluss_datum}</p>
          </div>
        )}
        {wp.beschluss_tagesordnungspunkt && (
          <div>
            <span className="text-gray-500">Tagesordnungspunkt</span>
            <p className="font-medium">{wp.beschluss_tagesordnungspunkt}</p>
          </div>
        )}
        {wp.bemerkung && (
          <div className="col-span-2">
            <span className="text-gray-500">Bemerkung</span>
            <p>{wp.bemerkung}</p>
          </div>
        )}
      </div>

      {/* Summen */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 grid grid-cols-3 gap-4 text-sm">
        <div className="text-center">
          <p className="text-gray-500 text-xs mb-1">Gesamtvolumen (Jahr)</p>
          <p className="text-lg font-bold">{fmt(wp.gesamtsumme)} €</p>
        </div>
        <div className="text-center">
          <p className="text-gray-500 text-xs mb-1">davon Hausgeld</p>
          <p className="text-lg font-semibold">{fmt(wp.gesamtsumme_hausgeld)} €</p>
        </div>
        <div className="text-center">
          <p className="text-gray-500 text-xs mb-1">Monats-Soll gesamt</p>
          <p className="text-lg font-semibold">{(Number(wp.gesamtsumme) / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })} €</p>
        </div>
      </div>

      {/* Beschluss-Panel (nur bei Entwurf) */}
      {istBearbeitbar && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
            <span className="font-medium text-gray-700 text-sm">Beschluss durchführen</span>
            {!beschlussOffen && (
              <button
                onClick={() => setBeschlussOffen(true)}
                className="px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700"
              >
                Beschluss durchführen
              </button>
            )}
          </div>
          {beschlussOffen && (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Beschluss-Datum *</label>
                  <input
                    type="date"
                    value={beschlussDatum}
                    onChange={e => setBeschlussDatum(e.target.value)}
                    className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tagesordnungspunkt (optional)</label>
                  <input
                    type="text"
                    value={top}
                    onChange={e => setTop(e.target.value)}
                    placeholder="z.B. TOP 5 ETV 14.03.2026"
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bemerkung (optional)</label>
                <textarea
                  value={bemerkung}
                  onChange={e => setBemerkung(e.target.value)}
                  rows={2}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                />
              </div>
              {beschlussError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-2 rounded">
                  {beschlussError}
                </div>
              )}
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setBeschlussOffen(false); setBeschlussError(null) }}
                  className="px-3 py-1.5 border border-gray-300 text-sm rounded hover:bg-gray-50"
                >
                  Abbrechen
                </button>
                <button
                  onClick={() => beschlussMut.mutate()}
                  disabled={!beschlussDatum || beschlussMut.isPending}
                  className="px-4 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
                >
                  {beschlussMut.isPending ? 'Buche...' : 'Beschluss bestätigen'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Positionen */}
      {wp.positionen.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-200 font-medium text-gray-700 text-sm">
            WP-Positionen ({wp.positionen.length})
          </div>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-gray-600">Konto</th>
                <th className="px-4 py-2 text-left font-medium text-gray-600">VS</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Jahresbetrag €</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Monatlich €</th>
                <th className="px-4 py-2 text-center font-medium text-gray-600">Verteilung</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {wp.positionen.map(pos => (
                <tr key={pos.id}>
                  <td className="px-4 py-2">
                    <span className="font-mono text-xs text-gray-500 mr-2">{pos.konto_nr}</span>
                    {pos.konto_name}
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">{pos.vs_code}</td>
                  <td className="px-4 py-2 text-right font-mono">{fmt(pos.betrag)}</td>
                  <td className="px-4 py-2 text-right font-mono text-gray-600">
                    {(Number(pos.betrag) / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-2 text-center text-xs">
                    {pos.verteilung_validiert ? (
                      <span className="text-green-600">🟢 validiert</span>
                    ) : pos.verteilung_freigegeben_trotz_diff ? (
                      <span className="text-yellow-600">🟡 freigegeben</span>
                    ) : (
                      <span className="text-gray-400">⚪ ausstehend</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-gray-300 bg-gray-50">
              <tr>
                <td colSpan={2} className="px-4 py-2 font-bold text-sm">GESAMT</td>
                <td className="px-4 py-2 text-right font-bold font-mono">{fmt(wp.gesamtsumme)}</td>
                <td className="px-4 py-2 text-right font-bold font-mono text-gray-600">
                  {(Number(wp.gesamtsumme) / 12).toLocaleString('de-DE', { minimumFractionDigits: 2 })}
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
