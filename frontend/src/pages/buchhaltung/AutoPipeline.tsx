import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { AutoLaufStatus } from '../../types'

const STATUS_LABEL: Record<AutoLaufStatus, string> = {
  erfolg:          'Erfolg',
  teilweise_erfolg:'Teilw. Erfolg',
  fehler:          'Fehler',
  uebersprungen:   'Übersprungen',
}

const STATUS_COLOR: Record<AutoLaufStatus, string> = {
  erfolg:          'bg-green-100 text-green-800',
  teilweise_erfolg:'bg-yellow-100 text-yellow-800',
  fehler:          'bg-red-100 text-red-800',
  uebersprungen:   'bg-gray-100 text-gray-600',
}

function StatusBadge({ status }: { status: AutoLaufStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}

function fmt(val: string) {
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function AutoPipeline() {
  const { data: einstellungen, isLoading: einstellungenLoading } = useQuery({
    queryKey: ['auto-pipeline-einstellungen'],
    queryFn: buchhaltungApi.autoPipelineEinstellungen,
  })

  const { data: protokolle = [], isLoading: protokolleLoading } = useQuery({
    queryKey: ['auto-pipeline-protokolle'],
    queryFn: () => buchhaltungApi.autoPipelineProtokolle(),
  })

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Auto-Pipeline Hausgeld</h1>

      {/* Einstellungen-Panel */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Status</p>
          {einstellungenLoading ? (
            <span className="text-gray-400 text-sm">…</span>
          ) : (
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-sm font-semibold ${
              einstellungen?.aktiv ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}>
              {einstellungen?.aktiv ? 'Aktiv' : 'Deaktiviert'}
            </span>
          )}
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Nächster Lauf</p>
          <p className="text-sm font-medium text-gray-800">
            {einstellungen ? new Date(einstellungen.naechster_lauf).toLocaleDateString('de-DE') : '…'}
          </p>
          <p className="text-xs text-gray-400">tägl. 02:00 Uhr (Stichtag {einstellungen?.stichtag}.)</p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">Aktive Objekte</p>
          <p className="text-2xl font-bold text-primary-600">
            {einstellungen?.aktive_objekte ?? '…'}
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 mb-1">SEPA-Vorlauf</p>
          <p className="text-sm font-medium text-gray-800">
            {einstellungen ? `${einstellungen.vorlauf_bd} Bankarbeitstage` : '…'}
          </p>
          <p className="text-xs text-gray-400 truncate" title={einstellungen?.sepa_output_dir}>
            {einstellungen?.sepa_output_dir ?? ''}
          </p>
        </div>
      </div>

      {/* Läufe-Tabelle */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="font-semibold text-gray-700">Letzte Läufe</h2>
        </div>

        {protokolleLoading ? (
          <p className="p-5 text-gray-400 text-sm">Laden…</p>
        ) : protokolle.length === 0 ? (
          <p className="p-5 text-gray-400 text-sm">Noch keine Läufe vorhanden.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-4 py-2 font-medium text-gray-600">Ausgeführt am</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Objekt</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Periode</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Status</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">EVs</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">Summe Sollst.</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">Summe LS</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {protokolle.map(p => (
                <tr key={p.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2 text-gray-700 whitespace-nowrap">
                    {new Date(p.ausgefuehrt_am).toLocaleString('de-DE', {
                      day: '2-digit', month: '2-digit', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  <td className="px-4 py-2 text-gray-800 font-medium">
                    <span className="font-mono text-xs text-gray-500 mr-1">{p.objekt_nummer}</span>
                    {p.objekt_bezeichnung}
                  </td>
                  <td className="px-4 py-2 text-gray-700 font-mono">
                    {new Date(p.periode).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' })}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={p.status} />
                    {p.warnungen.length > 0 && (
                      <span className="ml-1 text-xs text-yellow-600">{p.warnungen.length} Warn.</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600">
                    {p.anzahl_evs_erfolgreich}/{p.anzahl_evs_geplant}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-gray-700">
                    {parseFloat(p.summe_sollstellungen) > 0 ? `${fmt(p.summe_sollstellungen)} €` : '–'}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-gray-700">
                    {parseFloat(p.summe_lastschrift) > 0 ? `${fmt(p.summe_lastschrift)} €` : '–'}
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      to={`/buchhaltung/auto-pipeline/protokoll/${p.id}`}
                      className="text-primary-600 hover:underline text-xs"
                    >
                      Detail →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
