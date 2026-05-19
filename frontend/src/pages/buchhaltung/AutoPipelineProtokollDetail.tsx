import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { buchhaltungApi } from '../../api/buchhaltung'
import type { AutoLaufStatus } from '../../types'

const STATUS_COLOR: Record<AutoLaufStatus, string> = {
  erfolg:          'bg-green-100 text-green-800',
  teilweise_erfolg:'bg-yellow-100 text-yellow-800',
  fehler:          'bg-red-100 text-red-800',
  uebersprungen:   'bg-gray-100 text-gray-600',
}
const STATUS_LABEL: Record<AutoLaufStatus, string> = {
  erfolg:          'Erfolg',
  teilweise_erfolg:'Teilweise Erfolg',
  fehler:          'Fehler',
  uebersprungen:   'Übersprungen',
}

const WARNUNG_LABEL: Record<string, string> = {
  kein_sepa_mandat:          'SEPA-Mandat fehlt',
  keine_iban:                'Keine IBAN',
  keine_hausgeldhistorie:    'Kein Hausgeldsatz',
  mandat_typ_frst:           'FRST-Mandat',
  sepa_frist_unterschritten: 'SEPA-Frist unterschritten',
  dateischreibfehler:        'Dateischreibfehler',
}

function fmt(val: string) {
  return parseFloat(val).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-semibold text-gray-800 mt-0.5">{value}</p>
    </div>
  )
}

export function AutoPipelineProtokollDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: protokoll, isLoading } = useQuery({
    queryKey: ['auto-pipeline-protokoll', id],
    queryFn: () => buchhaltungApi.autoPipelineProtokoll(id!),
    enabled: !!id,
  })

  function handleDownload() {
    if (!id) return
    buchhaltungApi.autoPipelineDownloadPain008(id).then(blob => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = protokoll?.datei_pfad?.split(/[/\\]/).pop() ?? 'pain008.xml'
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  if (isLoading) return <p className="text-gray-400 p-6">Laden…</p>
  if (!protokoll) return <p className="text-gray-500 p-6">Protokoll nicht gefunden.</p>

  const periode = new Date(protokoll.periode).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })
  const ausgefuehrtAm = new Date(protokoll.ausgefuehrt_am).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/buchhaltung/auto-pipeline" className="text-primary-600 hover:underline text-sm">
          ← Auto-Pipeline
        </Link>
        <span className="text-gray-300">|</span>
        <h1 className="text-xl font-bold text-gray-900">
          Lauf {protokoll.objekt_bezeichnung} — {periode}
        </h1>
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-sm font-semibold ${STATUS_COLOR[protokoll.status]}`}>
          {STATUS_LABEL[protokoll.status]}
        </span>
      </div>

      {/* Stats */}
      <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <Stat label="Ausgeführt am" value={ausgefuehrtAm} />
          <Stat label="Objekt" value={`${protokoll.objekt_nummer} ${protokoll.objekt_bezeichnung}`} />
          <Stat label="Periode" value={periode} />
          <Stat label="EVs (geplant / erfolgreich / übersprungen)"
            value={`${protokoll.anzahl_evs_geplant} / ${protokoll.anzahl_evs_erfolgreich} / ${protokoll.anzahl_evs_uebersprungen}`} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Summe Sollstellungen" value={`${fmt(protokoll.summe_sollstellungen)} €`} />
          <Stat label="Summe Lastschrift (pain.008)" value={parseFloat(protokoll.summe_lastschrift) > 0 ? `${fmt(protokoll.summe_lastschrift)} €` : '–'} />
          {protokoll.sollstellungslauf && (
            <div>
              <p className="text-xs text-gray-500">Sollstellungslauf</p>
              <Link
                to={`/buchhaltung/sollstellungen`}
                className="text-sm text-primary-600 hover:underline mt-0.5 block font-mono"
              >
                {protokoll.sollstellungslauf.slice(0, 8)}… →
              </Link>
            </div>
          )}
          {protokoll.lastschriftlauf ? (
            <div>
              <p className="text-xs text-gray-500">Lastschriftlauf</p>
              <Link
                to={`/zahlungsverkehr/lastschrift`}
                className="text-sm text-primary-600 hover:underline mt-0.5 block font-mono"
              >
                {protokoll.lastschriftlauf.slice(0, 8)}… →
              </Link>
            </div>
          ) : (
            <div>
              <p className="text-xs text-gray-500">Lastschriftlauf</p>
              <p className="text-sm text-gray-400 mt-0.5">Kein Lauf erstellt</p>
            </div>
          )}
        </div>
      </div>

      {/* Datei */}
      {protokoll.datei_pfad && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
          <h2 className="font-semibold text-gray-700 mb-3">pain.008-Datei</h2>
          <div className="flex items-center gap-3">
            <code className="flex-1 text-xs bg-gray-50 border border-gray-200 rounded px-3 py-2 font-mono text-gray-700 truncate">
              {protokoll.datei_pfad}
            </code>
            <button
              onClick={handleDownload}
              className="flex-shrink-0 bg-primary-600 text-white px-4 py-2 rounded text-sm hover:bg-primary-700 transition-colors"
            >
              Herunterladen
            </button>
            <button
              onClick={() => {
                navigator.clipboard.writeText(protokoll.datei_pfad ?? '')
              }}
              className="flex-shrink-0 border border-gray-300 text-gray-600 px-3 py-2 rounded text-sm hover:bg-gray-50 transition-colors"
              title="Pfad kopieren"
            >
              Kopieren
            </button>
          </div>
        </div>
      )}

      {/* Warnungen */}
      {protokoll.warnungen.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
          <h2 className="font-semibold text-gray-700 mb-3">
            Warnungen ({protokoll.warnungen.length})
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-2 font-medium text-gray-600">Typ</th>
                <th className="text-left py-2 font-medium text-gray-600">Eigentümer</th>
                <th className="text-left py-2 font-medium text-gray-600">Einheit</th>
                <th className="text-left py-2 font-medium text-gray-600">Nachricht</th>
              </tr>
            </thead>
            <tbody>
              {protokoll.warnungen.map((w, i) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="py-2 pr-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                      {WARNUNG_LABEL[w.warnung_typ] ?? w.warnung_typ}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-gray-700">{w.name ?? '–'}</td>
                  <td className="py-2 pr-3 text-gray-500 font-mono">{w.einheit ?? '–'}</td>
                  <td className="py-2 text-gray-600 text-xs">{w.nachricht}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Fehler */}
      {protokoll.fehler && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-5 mb-4">
          <h2 className="font-semibold text-red-700 mb-2">Fehler-Details</h2>
          <pre className="text-xs text-red-600 whitespace-pre-wrap font-mono overflow-auto max-h-64">
            {protokoll.fehler}
          </pre>
        </div>
      )}
    </div>
  )
}
