import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { wirtschaftsplanApi } from '../../../api/wirtschaftsplan'

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
