import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { personenApi, type CsvVorschauRow } from '../../api/personen'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'

const TYP_LABEL: Record<string, string> = {
  '100': 'Eigentümer',
  '200': 'Mieter',
  '300': 'Kreditor',
  '400': 'Sonstiges',
}

type Phase = 'upload' | 'vorschau' | 'ergebnis'

interface ErgebnisState {
  importiert: number
  abgelehnt: number
  errors: string[]
}

// ------------------------------------------------------------------
// Status-Indikatoren
// ------------------------------------------------------------------
function StatusIcon({ status }: { status: CsvVorschauRow['status'] }) {
  if (status === 'neu') {
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-600 text-sm font-bold" title="Korrekt">
        ✓
      </span>
    )
  }
  if (status === 'duplikat') {
    return (
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-orange-100 text-orange-600 text-sm font-bold" title="Mögliche Dublette">
        ⚠
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-100 text-red-600 text-sm font-bold" title="Fehler">
      ✕
    </span>
  )
}

function rowBg(status: CsvVorschauRow['status']) {
  if (status === 'neu') return 'bg-green-50'
  if (status === 'duplikat') return 'bg-orange-50'
  return 'bg-red-50'
}

// ------------------------------------------------------------------
// Haupt-Komponente
// ------------------------------------------------------------------
export function PersonenImport() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)

  const [phase, setPhase] = useState<Phase>('upload')
  const [isLoading, setIsLoading] = useState(false)
  const [fatalErrors, setFatalErrors] = useState<string[]>([])
  const [rows, setRows] = useState<CsvVorschauRow[]>([])
  const [ergebnis, setErgebnis] = useState<ErgebnisState | null>(null)

  // ------------------------------------------------------------------
  // Vorlage herunterladen
  // ------------------------------------------------------------------
  const handleVorlage = async () => {
    const blob = await personenApi.csvVorlage()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'IMMOCORE_Personen_Vorlage.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  // ------------------------------------------------------------------
  // Datei hochladen → Vorschau
  // ------------------------------------------------------------------
  const handleFile = async (file: File) => {
    setIsLoading(true)
    setFatalErrors([])
    try {
      const result = await personenApi.csvVorschau(file)
      if (result.errors.length > 0 && result.rows.length === 0) {
        setFatalErrors(result.errors)
      } else {
        setRows(result.rows)
        setPhase('vorschau')
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { errors?: string[] } } }
      const msgs = axiosErr?.response?.data?.errors
      setFatalErrors(msgs?.length ? msgs : ['Fehler beim Verarbeiten der Datei.'])
    } finally {
      setIsLoading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  // ------------------------------------------------------------------
  // Aktion togglen
  // ------------------------------------------------------------------
  const setAktion = (zeile: number, aktion: 'importieren' | 'ablehnen') => {
    setRows(prev => prev.map(r => r.zeile === zeile ? { ...r, aktion } : r))
  }

  const setAlleAktion = (aktion: 'importieren' | 'ablehnen') => {
    setRows(prev => prev.map(r => r.status === 'fehler' ? r : { ...r, aktion }))
  }

  // ------------------------------------------------------------------
  // Import starten
  // ------------------------------------------------------------------
  const handleImport = async () => {
    setIsLoading(true)
    try {
      const payload = rows.map(r => ({ zeile: r.zeile, csv_data: r.csv_data, aktion: r.aktion }))
      const result = await personenApi.csvImport(payload)
      setErgebnis(result)
      setPhase('ergebnis')
    } catch {
      setFatalErrors(['Fehler beim Import. Bitte erneut versuchen.'])
    } finally {
      setIsLoading(false)
    }
  }

  const neuCount = rows.filter(r => r.status === 'neu').length
  const dupCount = rows.filter(r => r.status === 'duplikat').length
  const errCount = rows.filter(r => r.status === 'fehler').length
  const importCount = rows.filter(r => r.aktion === 'importieren').length
  const ablehnCount = rows.filter(r => r.aktion === 'ablehnen').length

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => navigate('/personen')}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          ← Personen
        </button>
        <h1 className="text-2xl font-bold text-gray-900">CSV-Import Personen</h1>
      </div>

      {/* ============================================================
          Phase: Upload
      ============================================================ */}
      {phase === 'upload' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleVorlage}
              className="text-sm text-primary-600 hover:text-primary-700 underline"
            >
              CSV-Vorlage herunterladen
            </button>
            <span className="text-gray-300">|</span>
            <span className="text-sm text-gray-500">
              Spalten: person_typ; ist_firma; Firma; Anrede; Vorname1; Nachname1; …
            </span>
          </div>

          <div
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-gray-300 rounded-xl p-12 text-center cursor-pointer hover:border-primary-400 hover:bg-primary-50 transition-colors"
          >
            <div className="text-4xl text-gray-300 mb-3">📂</div>
            <p className="text-gray-600 font-medium">CSV-Datei hier ablegen</p>
            <p className="text-sm text-gray-400 mt-1">oder klicken zum Auswählen</p>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={handleInputChange}
            />
          </div>

          {isLoading && <p className="text-sm text-gray-500 text-center">Datei wird verarbeitet…</p>}

          {fatalErrors.length > 0 && (
            <div className="rounded-md bg-red-50 border border-red-200 p-4 space-y-1">
              <p className="text-sm font-medium text-red-700">Fehler beim Einlesen:</p>
              {fatalErrors.map((e, i) => <p key={i} className="text-sm text-red-600">{e}</p>)}
            </div>
          )}
        </div>
      )}

      {/* ============================================================
          Phase: Vorschau
      ============================================================ */}
      {phase === 'vorschau' && (
        <div className="space-y-4">

          {/* Zusammenfassung */}
          <div className="flex flex-wrap items-center gap-4 bg-gray-50 rounded-lg p-3 text-sm">
            <span className="text-gray-600 font-medium">{rows.length} Zeilen eingelesen</span>
            <span className="flex items-center gap-1.5 text-green-700">
              <span className="w-4 h-4 rounded-full bg-green-100 text-green-600 text-xs font-bold flex items-center justify-center">✓</span>
              {neuCount} korrekt
            </span>
            {dupCount > 0 && (
              <span className="flex items-center gap-1.5 text-orange-600">
                <span className="w-4 h-4 rounded-full bg-orange-100 text-orange-600 text-xs font-bold flex items-center justify-center">⚠</span>
                {dupCount} Dublette{dupCount !== 1 ? 'n' : ''}
              </span>
            )}
            {errCount > 0 && (
              <span className="flex items-center gap-1.5 text-red-600">
                <span className="w-4 h-4 rounded-full bg-red-100 text-red-600 text-xs font-bold flex items-center justify-center">✕</span>
                {errCount} Fehler
              </span>
            )}
            <div className="ml-auto flex gap-2">
              <button
                type="button"
                onClick={() => setAlleAktion('importieren')}
                className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50"
              >
                Alle importieren
              </button>
              <button
                type="button"
                onClick={() => setAlleAktion('ablehnen')}
                className="text-xs px-2 py-1 rounded border border-red-300 text-red-600 hover:bg-red-50"
              >
                Alle ablehnen
              </button>
            </div>
          </div>

          {/* Vorschau-Tabelle */}
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm min-w-[700px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-center px-3 py-2 font-medium text-gray-600 w-10">Z.</th>
                  <th className="text-center px-3 py-2 font-medium text-gray-600 w-10"></th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">Name / Firma</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-28">Typ</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600">E-Mail</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 w-40">Aktion</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => {
                  const d = row.csv_data
                  const displayName = d.ist_firma
                    ? d.firmenname
                    : [d.vorname, d.nachname].filter(Boolean).join(' ')
                  const isFehler = row.status === 'fehler'
                  const isDup = row.status === 'duplikat'

                  return (
                    <React.Fragment key={row.zeile}>
                      {/* Hauptzeile */}
                      <tr className={`border-t border-gray-100 ${rowBg(row.status)}`}>
                        <td className="px-3 py-2 text-center text-gray-400 text-xs">{row.zeile}</td>
                        <td className="px-3 py-2 text-center">
                          <StatusIcon status={row.status} />
                        </td>
                        <td className="px-3 py-2 font-medium text-gray-800">
                          {displayName || <span className="text-gray-400 italic text-xs">–</span>}
                        </td>
                        <td className="px-3 py-2">
                          <Badge value={TYP_LABEL[d.person_typ] ?? d.person_typ} />
                        </td>
                        <td className="px-3 py-2 text-gray-600 text-xs">{d.email || '–'}</td>
                        <td className="px-3 py-2">
                          {isFehler ? (
                            <span className="text-xs text-red-400 italic">nicht importierbar</span>
                          ) : (
                            <div className="flex rounded overflow-hidden border border-gray-200 text-xs w-fit">
                              <button
                                type="button"
                                onClick={() => setAktion(row.zeile, 'importieren')}
                                className={`px-2 py-1 transition-colors ${row.aktion === 'importieren' ? 'bg-green-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                              >
                                Importieren
                              </button>
                              <button
                                type="button"
                                onClick={() => setAktion(row.zeile, 'ablehnen')}
                                className={`px-2 py-1 border-l border-gray-200 transition-colors ${row.aktion === 'ablehnen' ? 'bg-red-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                              >
                                Ablehnen
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>

                      {/* Fehler-Details */}
                      {isFehler && row.fehler.length > 0 && (
                        <tr className={`border-t border-red-100 ${rowBg(row.status)}`}>
                          <td colSpan={2} />
                          <td colSpan={4} className="px-3 pb-2.5">
                            <div className="rounded bg-red-100 border border-red-200 px-3 py-2 space-y-1">
                              {row.fehler.map((f, fi) => (
                                <p key={fi} className="text-xs text-red-700 flex items-start gap-1.5">
                                  <span className="mt-0.5 shrink-0">•</span>
                                  {f}
                                </p>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}

                      {/* Dubletten-Details */}
                      {isDup && row.duplikat && (
                        <tr className={`border-t border-orange-100 ${rowBg(row.status)}`}>
                          <td colSpan={2} />
                          <td colSpan={4} className="px-3 pb-2.5">
                            <div className="rounded bg-orange-100 border border-orange-200 px-3 py-2 space-y-0.5">
                              <p className="text-xs font-medium text-orange-700">{row.duplikat.grund}</p>
                              {row.duplikat.quelle === 'datenbank' ? (
                                <p className="text-xs text-orange-600">
                                  In der Datenbank: <strong>{row.duplikat.name}</strong>
                                  {row.duplikat.personennummer && <> · Nr.&nbsp;{row.duplikat.personennummer}</>}
                                  {row.duplikat.email && <> · {row.duplikat.email}</>}
                                </p>
                              ) : (
                                <p className="text-xs text-orange-600">
                                  In dieser Datei (Zeile {row.duplikat.zeile_ref}): <strong>{row.duplikat.name}</strong>
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Aktionsleiste */}
          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={() => { setPhase('upload'); setRows([]); setFatalErrors([]) }}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← Andere Datei wählen
            </button>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-500">
                {importCount} importieren · {ablehnCount} ablehnen
              </span>
              <Button onClick={handleImport} disabled={isLoading || importCount === 0}>
                {isLoading ? 'Importiere…' : `${importCount} Person${importCount !== 1 ? 'en' : ''} importieren`}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================
          Phase: Ergebnis
      ============================================================ */}
      {phase === 'ergebnis' && ergebnis && (
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-200 p-6 bg-white space-y-4">
            <h2 className="text-lg font-semibold text-gray-800">Import abgeschlossen</h2>

            <div className="grid grid-cols-3 gap-4">
              <div className="text-center rounded-lg bg-green-50 border border-green-100 p-4">
                <p className="text-3xl font-bold text-green-600">{ergebnis.importiert}</p>
                <p className="text-sm text-green-700 mt-1">Importiert</p>
              </div>
              <div className="text-center rounded-lg bg-gray-50 border border-gray-100 p-4">
                <p className="text-3xl font-bold text-gray-500">{ergebnis.abgelehnt}</p>
                <p className="text-sm text-gray-600 mt-1">Abgelehnt</p>
              </div>
              <div className="text-center rounded-lg bg-red-50 border border-red-100 p-4">
                <p className="text-3xl font-bold text-red-500">{ergebnis.errors.length}</p>
                <p className="text-sm text-red-600 mt-1">Fehler</p>
              </div>
            </div>

            {ergebnis.errors.length > 0 && (
              <div className="rounded-md bg-red-50 border border-red-200 p-3 space-y-1">
                <p className="text-sm font-medium text-red-700">Fehler beim Import:</p>
                {ergebnis.errors.map((e, i) => <p key={i} className="text-sm text-red-600">{e}</p>)}
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <Button onClick={() => navigate('/personen')}>
              Zur Personenliste
            </Button>
            <button
              type="button"
              onClick={() => { setPhase('upload'); setRows([]); setFatalErrors([]); setErgebnis(null) }}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2"
            >
              Weiteren Import durchführen
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
