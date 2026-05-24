import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { verteilerApi, VsInfo } from '../../api/verteiler'

interface Props {
  objektId: string
  onClose: () => void
}

export function VerteilerExportDialog({ objektId, onClose }: Props) {
  const { data: vsListe = [], isLoading } = useQuery({
    queryKey: ['verteiler-aktive-vs', objektId],
    queryFn: () => verteilerApi.aktiveVs(objektId),
  })

  // {code: wj_id} für Verbrauchs-VS
  const [ausgewaehlte, setAusgewaehlte] = useState<Set<string>>(new Set())
  const [wjAuswahl, setWjAuswahl] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)

  const toggleVs = (code: string, vs: VsInfo) => {
    setAusgewaehlte(prev => {
      const next = new Set(prev)
      if (next.has(code)) {
        next.delete(code)
      } else {
        next.add(code)
        // Default-WJ für Verbrauchs-VS: erstes offenes, sonst erstes
        if (vs.kategorie === 'verbrauch' && vs.wirtschaftsjahre.length > 0) {
          const offenes = vs.wirtschaftsjahre.find(wj => wj.status === 'offen')
          setWjAuswahl(wa => ({ ...wa, [code]: (offenes ?? vs.wirtschaftsjahre[0]).id }))
        }
      }
      return next
    })
  }

  const alleAuswaehlen = () => {
    const next = new Set(vsListe.map(v => v.code))
    setAusgewaehlte(next)
    const wjMap: Record<string, string> = {}
    vsListe.forEach(vs => {
      if (vs.kategorie === 'verbrauch' && vs.wirtschaftsjahre.length > 0) {
        const offenes = vs.wirtschaftsjahre.find(wj => wj.status === 'offen')
        wjMap[vs.code] = (offenes ?? vs.wirtschaftsjahre[0]).id
      }
    })
    setWjAuswahl(wjMap)
  }

  const umkehren = () => {
    const next = new Set(vsListe.map(v => v.code).filter(c => !ausgewaehlte.has(c)))
    setAusgewaehlte(next)
  }

  const handleExport = async () => {
    if (ausgewaehlte.size === 0) return
    setFehler(null)
    setLoading(true)
    try {
      const vsCodes = Array.from(ausgewaehlte).map(code => {
        const vs = vsListe.find(v => v.code === code)!
        return vs.kategorie === 'verbrauch'
          ? { code, wj_id: wjAuswahl[code] }
          : { code }
      })
      const blob = await verteilerApi.exportZip(objektId, vsCodes)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `VS_Export_${new Date().toISOString().slice(0, 10)}.zip`
      a.click()
      URL.revokeObjectURL(url)
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      setFehler(msg ?? 'Export fehlgeschlagen.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">Verteilerschlüssel exportieren</h2>
        </div>

        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
          {isLoading && <p className="text-sm text-gray-500">Lade aktive Verteilerschlüssel…</p>}
          {!isLoading && vsListe.length === 0 && (
            <p className="text-sm text-gray-500">Keine aktiven Verteilerschlüssel am Objekt.</p>
          )}
          {!isLoading && vsListe.length > 0 && (
            <>
              <p className="text-xs font-medium text-gray-500 mb-3">Aktive Verteilerschlüssel am Objekt:</p>
              <div className="space-y-2">
                {vsListe.map(vs => {
                  const checked = ausgewaehlte.has(vs.code)
                  const ohneWj = vs.kategorie !== 'verbrauch' || vs.wirtschaftsjahre.length === 0
                  return (
                    <div key={vs.code} className="flex items-center gap-3 py-1">
                      <input
                        type="checkbox"
                        id={`vs-${vs.code}`}
                        checked={checked}
                        disabled={vs.kategorie === 'verbrauch' && vs.wirtschaftsjahre.length === 0}
                        onChange={() => toggleVs(vs.code, vs)}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600"
                      />
                      <label htmlFor={`vs-${vs.code}`} className="flex-1 flex items-center gap-2 cursor-pointer">
                        <span className="font-mono text-sm font-medium text-gray-700 w-8">{vs.code}</span>
                        <span className="text-sm text-gray-700">{vs.bezeichnung}</span>
                      </label>
                      {ohneWj ? (
                        <span className="text-xs text-gray-400">(ältestes WJ)</span>
                      ) : vs.wirtschaftsjahre.length === 0 ? (
                        <span className="text-xs text-red-400">Kein Wirtschaftsjahr vorhanden</span>
                      ) : (
                        <select
                          className="text-xs border border-gray-200 rounded px-1 py-0.5"
                          value={wjAuswahl[vs.code] ?? ''}
                          disabled={!checked}
                          onChange={e => setWjAuswahl(wa => ({ ...wa, [vs.code]: e.target.value }))}
                        >
                          {vs.wirtschaftsjahre.map(wj => (
                            <option key={wj.id} value={wj.id}>WJ {wj.jahr}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  )
                })}
              </div>

              <div className="flex gap-2 mt-4">
                <button
                  type="button"
                  onClick={alleAuswaehlen}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Alle auswählen
                </button>
                <button
                  type="button"
                  onClick={umkehren}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Auswahl umkehren
                </button>
              </div>
            </>
          )}

          {fehler && (
            <div className="mt-3 rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {fehler}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={ausgewaehlte.size === 0 || loading}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40"
          >
            {loading ? 'Exportiere…' : 'Export'}
          </button>
        </div>
      </div>
    </div>
  )
}
