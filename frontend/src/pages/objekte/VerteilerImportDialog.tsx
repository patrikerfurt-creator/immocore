import { useRef, useState } from 'react'
import { verteilerApi, ImportVorschau, ImportZeile } from '../../api/verteiler'

interface Props {
  objektId: string
  onClose: () => void
  onSuccess?: () => void
}

const STATUS_LABEL: Record<ImportZeile['status'], string> = {
  neu:          'Neu',
  geaendert:    'Geändert',
  unveraendert: 'Unverändert',
  leer:         'Leer',
  ungueltig:    'Ungültig',
}

const STATUS_COLOR: Record<ImportZeile['status'], string> = {
  neu:          'bg-green-100 text-green-800',
  geaendert:    'bg-blue-100 text-blue-800',
  unveraendert: 'bg-gray-100 text-gray-500',
  leer:         'bg-gray-100 text-gray-400',
  ungueltig:    'bg-red-100 text-red-800',
}

function _fmt(val: string | null): string {
  if (val === null) return '— (leer)'
  const n = parseFloat(val)
  if (isNaN(n)) return val
  return n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

export function VerteilerImportDialog({ objektId, onClose, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [phase, setPhase] = useState<'upload' | 'preview' | 'loading'>('upload')
  const [vorschau, setVorschau] = useState<ImportVorschau | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const [commitLoading, setCommitLoading] = useState(false)
  const [erfolg, setErfolg] = useState<number | null>(null)

  const handleDateiWaehlen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const datei = e.target.files?.[0]
    if (!datei) return
    setFehler(null)
    setPhase('loading')
    try {
      const data = await verteilerApi.importPreview(objektId, datei)
      setVorschau(data)
      setPhase('preview')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setFehler(msg ?? 'Datei konnte nicht verarbeitet werden.')
      setPhase('upload')
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleCommit = async () => {
    if (!vorschau || vorschau.hat_fehler) return
    setCommitLoading(true)
    try {
      const result = await verteilerApi.importCommit(objektId, vorschau.preview_token)
      setErfolg(result.anzahl_aktualisiert)
      onSuccess?.()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setFehler(msg ?? 'Import fehlgeschlagen.')
    } finally {
      setCommitLoading(false)
    }
  }

  const istStammWsWarnung = vorschau?.warnungen.some(w => w.includes('überschreiben'))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl mx-4 max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-lg font-semibold text-gray-800">
            {vorschau
              ? `Vorschau Import VS ${vorschau.vs_code}${vorschau.wj_jahr ? ` — WJ ${vorschau.wj_jahr}` : ''}`
              : 'Verteilerschlüssel importieren'}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* Erfolg */}
          {erfolg !== null && (
            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
              Import erfolgreich: <strong>{erfolg}</strong> Einheit(en) aktualisiert.
            </div>
          )}

          {/* Upload-Phase */}
          {phase === 'upload' && erfolg === null && (
            <div>
              <p className="text-sm text-gray-600 mb-4">
                Wählen Sie eine .xlsx-Datei aus (max. 5 MB), die vom System exportiert wurde.
              </p>
              <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors">
                <span className="text-sm text-gray-500">Klicken zum Auswählen</span>
                <span className="text-xs text-gray-400 mt-1">.xlsx, max. 5 MB</span>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx"
                  onChange={handleDateiWaehlen}
                  className="hidden"
                />
              </label>
            </div>
          )}

          {/* Lade-Spinner */}
          {phase === 'loading' && (
            <div className="flex items-center justify-center h-24">
              <span className="text-sm text-gray-500 animate-pulse">Datei wird verarbeitet…</span>
            </div>
          )}

          {/* Fehler */}
          {fehler && (
            <div className="mt-3 rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {fehler}
            </div>
          )}

          {/* Vorschau */}
          {phase === 'preview' && vorschau && (
            <div>
              {/* Warn-Banner Stamm-VS */}
              {istStammWsWarnung && (
                <div className="mb-3 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800 font-medium">
                  ⚠ {vorschau.warnungen.find(w => w.includes('überschreiben'))}
                </div>
              )}

              {/* Weitere Warnungen */}
              {vorschau.warnungen.filter(w => !w.includes('überschreiben')).map((w, i) => (
                <div key={i} className="mb-2 rounded bg-yellow-50 border border-yellow-200 px-3 py-2 text-xs text-yellow-800">
                  {w}
                </div>
              ))}

              {/* Fehler-Banner */}
              {vorschau.hat_fehler && (
                <div className="mb-3 rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  Die Datei enthält Fehler. Bitte korrigieren und erneut hochladen.
                </div>
              )}

              {/* Zusammenfassung */}
              <div className="flex flex-wrap gap-3 mb-3 text-xs text-gray-600">
                {Object.entries(vorschau.zusammenfassung).map(([s, n]) => n > 0 && (
                  <span key={s} className={`px-2 py-0.5 rounded font-medium ${STATUS_COLOR[s as ImportZeile['status']] ?? ''}`}>
                    {n} {STATUS_LABEL[s as ImportZeile['status']] ?? s}
                  </span>
                ))}
              </div>

              {/* Tabelle */}
              <div className="overflow-x-auto rounded border border-gray-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Einheit</th>
                      <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">Bezeichnung</th>
                      <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">Alter Wert</th>
                      <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">Neuer Wert</th>
                      <th className="text-center px-3 py-2 text-xs font-medium text-gray-500">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vorschau.zeilen.map((z, i) => (
                      <tr
                        key={i}
                        className={`border-b border-gray-100 ${z.warnung ? 'bg-yellow-50' : ''} ${z.fehler ? 'bg-red-50' : ''}`}
                      >
                        <td className="px-3 py-1.5 font-mono text-xs text-gray-700">{z.einheit_nr}</td>
                        <td className="px-3 py-1.5 text-xs text-gray-600">{z.bezeichnung}</td>
                        <td className="px-3 py-1.5 text-right text-xs font-mono text-gray-500">
                          {_fmt(z.alter_wert)}
                        </td>
                        <td className="px-3 py-1.5 text-right text-xs font-mono text-gray-800">
                          {_fmt(z.neuer_wert)}
                        </td>
                        <td className="px-3 py-1.5 text-center">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[z.status]}`}>
                            {STATUS_LABEL[z.status]}
                          </span>
                          {z.fehler && <p className="text-xs text-red-600 mt-0.5">{z.fehler}</p>}
                          {z.warnung && <p className="text-xs text-yellow-700 mt-0.5">{z.warnung}</p>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex justify-between items-center flex-shrink-0">
          <div>
            {phase === 'preview' && erfolg === null && (
              <button
                type="button"
                onClick={() => { setPhase('upload'); setVorschau(null); setFehler(null) }}
                className="text-xs text-blue-600 hover:underline"
              >
                Andere Datei wählen
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
            >
              {erfolg !== null ? 'Schließen' : 'Abbrechen'}
            </button>
            {phase === 'preview' && vorschau && erfolg === null && (
              <button
                type="button"
                onClick={handleCommit}
                disabled={vorschau.hat_fehler || commitLoading}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40"
              >
                {commitLoading ? 'Importiere…' : 'Import bestätigen'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
