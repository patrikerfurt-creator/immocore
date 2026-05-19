import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { massenimportApi } from '../../api/massenimport'
import type { CommitResponse, PreviewResponse, ZeileVorschau } from '../../api/massenimport'
import { Button } from '../../components/ui/Button'

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: ZeileVorschau['status'] | 'uebersprungen' }) {
  const map: Record<string, string> = {
    ok:           'bg-green-100 text-green-700',
    warnung:      'bg-yellow-100 text-yellow-700',
    fehler:       'bg-red-100 text-red-700',
    uebersprungen:'bg-gray-100 text-gray-500',
  }
  const label: Record<string, string> = {
    ok: '✓ OK', warnung: '⚠ Warnung', fehler: '✗ Fehler', uebersprungen: '– Übersprungen',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {label[status] ?? status}
    </span>
  )
}

function SummaryCard({ label, value, color = 'gray' }: { label: string; value: number; color?: string }) {
  const colors: Record<string, string> = {
    green: 'bg-green-50 text-green-700 border-green-200',
    yellow:'bg-yellow-50 text-yellow-700 border-yellow-200',
    red:   'bg-red-50 text-red-600 border-red-200',
    gray:  'bg-gray-50 text-gray-700 border-gray-200',
    blue:  'bg-blue-50 text-blue-700 border-blue-200',
  }
  return (
    <div className={`rounded-lg border px-4 py-3 text-center ${colors[color]}`}>
      <div className="text-2xl font-bold">{value.toLocaleString('de-DE')}</div>
      <div className="text-xs mt-0.5">{label}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 1 — Vorlage herunterladen
// ---------------------------------------------------------------------------
function Schritt1({ onWeiter }: { onWeiter: () => void }) {
  const [loading, setLoading] = useState(false)

  const download = async () => {
    setLoading(true)
    try {
      const blob = await massenimportApi.vorlageHerunterladen()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = 'MI-WEG.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-5">
        <h3 className="font-semibold text-blue-800 mb-2">Schritt 1 — Vorlage herunterladen</h3>
        <p className="text-sm text-blue-700 mb-4">
          Laden Sie die Excel-Vorlage <strong>MI-WEG.xlsx</strong> herunter, füllen Sie sie aus
          und laden Sie sie im nächsten Schritt hoch. Pro Zeile wird ein WEG-Objekt angelegt.
        </p>
        <div className="text-sm text-blue-600 space-y-1 mb-4">
          <p>🟡 <strong>Pflicht:</strong> Bezeichnung, Anschrift 1, PLZ1, ORT1, ANZ-RL</p>
          <p>🟢 <strong>Optional:</strong> Weitere Eingänge (bis zu 10), Baujahr</p>
          <p>📋 <strong>ANZ-RL:</strong> Anzahl Rücklagen (0–21). Pro Rücklage werden 5 Sachkonten,
             1 Bankkonto und 1 Abrechnungsart angelegt.</p>
        </div>
        <Button onClick={download} disabled={loading}>
          {loading ? 'Wird geladen…' : '⬇ MI-WEG.xlsx herunterladen'}
        </Button>
      </div>
      <div className="flex justify-end">
        <Button onClick={onWeiter}>Weiter →</Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 2 — Upload
// ---------------------------------------------------------------------------
function Schritt2({ onWeiter }: { onWeiter: (file: File) => void }) {
  const [dragOver, setDragOver]   = useState(false)
  const [selected, setSelected]   = useState<File | null>(null)
  const [error, setError]         = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setError('Nur .xlsx-Dateien werden unterstützt.')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('Datei zu groß (max. 10 MB).')
      return
    }
    setError(null)
    setSelected(file)
  }

  return (
    <div className="space-y-6">
      <h3 className="font-semibold text-gray-800">Schritt 2 — Excel-Datei hochladen</h3>

      <div
        onDragOver={e  => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => {
          e.preventDefault()
          setDragOver(false)
          const f = e.dataTransfer.files[0]
          if (f) handleFile(f)
        }}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-primary-400 bg-primary-50' : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        }`}
      >
        <div className="text-4xl mb-2">📂</div>
        <p className="text-sm text-gray-600">
          Datei hier ablegen oder <span className="text-primary-600 font-medium">klicken zum Auswählen</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">Nur .xlsx, max. 10 MB, max. 500 Zeilen</p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />
      </div>

      {selected && (
        <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg">
          <span className="text-green-600 text-xl">📄</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">{selected.name}</p>
            <p className="text-xs text-gray-500">{(selected.size / 1024).toFixed(1)} KB</p>
          </div>
          <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-red-500">✕</button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <Button onClick={() => selected && onWeiter(selected)} disabled={!selected}>
          Datei prüfen →
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 3 — Vorschau
// ---------------------------------------------------------------------------
type FilterTyp = 'alle' | 'ok' | 'warnung' | 'fehler'

function Schritt3({
  preview, onWeiter, onZurueck,
}: {
  preview: PreviewResponse
  onWeiter: () => void
  onZurueck: () => void
}) {
  const [filter, setFilter] = useState<FilterTyp>('alle')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const toggle = (nr: number) =>
    setExpanded(prev => {
      const n = new Set(prev)
      n.has(nr) ? n.delete(nr) : n.add(nr)
      return n
    })

  const zeilen = filter === 'alle'
    ? preview.zeilen
    : preview.zeilen.filter(z => z.status === filter)

  const { summary } = preview
  const kannImportieren = summary.ok + summary.warnung > 0

  return (
    <div className="space-y-5">
      <h3 className="font-semibold text-gray-800">Schritt 3 — Vorschau &amp; Validierung</h3>

      {/* Zusammenfassung */}
      <div className="grid grid-cols-3 gap-3">
        <SummaryCard label="Korrekte Zeilen"  value={summary.ok}      color="green" />
        <SummaryCard label="Warnungen"         value={summary.warnung} color="yellow" />
        <SummaryCard label="Fehler"            value={summary.fehler}  color="red" />
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {(['alle', 'ok', 'warnung', 'fehler'] as FilterTyp[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              filter === f
                ? 'bg-primary-600 text-white border-primary-600'
                : 'border-gray-300 text-gray-600 hover:border-primary-400'
            }`}
          >
            {f === 'alle' ? `Alle (${summary.gesamt})` :
             f === 'ok'      ? `✓ OK (${summary.ok})` :
             f === 'warnung' ? `⚠ Warnungen (${summary.warnung})` :
                               `✗ Fehler (${summary.fehler})`}
          </button>
        ))}
      </div>

      {/* Tabelle */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2 text-gray-500 font-medium w-12">Zeile</th>
              <th className="text-left px-4 py-2 text-gray-500 font-medium">Bezeichnung</th>
              <th className="text-center px-3 py-2 text-gray-500 font-medium w-20">Eingänge</th>
              <th className="text-center px-3 py-2 text-gray-500 font-medium w-20">Rücklagen</th>
              <th className="text-center px-3 py-2 text-gray-500 font-medium w-20">Konten</th>
              <th className="text-left px-4 py-2 text-gray-500 font-medium w-32">Status</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {zeilen.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-gray-400">Keine Zeilen in diesem Filter.</td></tr>
            )}
            {zeilen.map(z => (
              <>
                <tr key={z.zeilennummer} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-400 font-mono text-xs">{z.zeilennummer}</td>
                  <td className="px-4 py-2 font-medium text-gray-800">{z.bezeichnung || <span className="text-gray-400 italic">leer</span>}</td>
                  <td className="px-3 py-2 text-center text-gray-600">{z.eingaenge_anzahl}</td>
                  <td className="px-3 py-2 text-center text-gray-600">{z.ruecklagen}</td>
                  <td className="px-3 py-2 text-center text-gray-600">{z.konten_anzahl}</td>
                  <td className="px-4 py-2"><StatusBadge status={z.status} /></td>
                  <td className="px-2 py-2 text-center">
                    {(z.meldungen.length > 0) && (
                      <button
                        onClick={() => toggle(z.zeilennummer)}
                        className="text-xs text-gray-400 hover:text-gray-600"
                      >
                        {expanded.has(z.zeilennummer) ? '▲' : '▼'}
                      </button>
                    )}
                  </td>
                </tr>
                {expanded.has(z.zeilennummer) && (
                  <tr key={`${z.zeilennummer}-detail`} className="bg-gray-50">
                    <td />
                    <td colSpan={6} className="px-4 py-2">
                      <ul className="space-y-0.5">
                        {z.meldungen.map((m, i) => (
                          <li key={i} className={`text-xs ${z.status === 'fehler' ? 'text-red-600' : 'text-yellow-700'}`}>
                            • {m}
                          </li>
                        ))}
                      </ul>
                      <div className="mt-2 text-xs text-gray-500 flex gap-4">
                        <span>Abrechnungsarten: {z.abrechnungsarten_anzahl}</span>
                        <span>Bankkonten: {1 + z.ruecklagen}</span>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between">
        <Button variant="secondary" onClick={onZurueck}>← Zurück</Button>
        <Button onClick={onWeiter} disabled={!kannImportieren}>
          Weiter zur Bestätigung →
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 4 — Bestätigung
// ---------------------------------------------------------------------------
function Schritt4({
  preview, onWeiter, onZurueck, loading,
}: {
  preview: PreviewResponse
  onWeiter: () => void
  onZurueck: () => void
  loading: boolean
}) {
  const { summary } = preview
  return (
    <div className="space-y-6">
      <h3 className="font-semibold text-gray-800">Schritt 4 — Import bestätigen</h3>

      {summary.fehler > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
          <strong>{summary.fehler} Zeile(n) mit Fehlern</strong> werden übersprungen.
          Nur die {summary.ok + summary.warnung} gültigen Zeilen werden importiert.
        </div>
      )}

      <div className="bg-white rounded-xl border p-6">
        <p className="text-sm text-gray-600 mb-5 font-medium">
          Folgende Objekte und Strukturen werden angelegt:
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <SummaryCard label="WEG-Objekte"       value={summary.objekte}          color="blue" />
          <SummaryCard label="Eingänge"           value={summary.liegenschaften}   color="blue" />
          <SummaryCard label="Bankkonten"         value={summary.bankkonten}       color="blue" />
          <SummaryCard label="Sachkonten"         value={summary.konten}           color="blue" />
          <SummaryCard label="Abrechnungsarten"   value={summary.abrechnungsarten} color="blue" />
        </div>
        <p className="mt-5 text-xs text-gray-400">
          Bankkonten werden mit Platzhalter-IBAN angelegt (DE00…) und müssen nachgepflegt werden.
          Einheiten, Eigentümer und Verträge sind <strong>nicht</strong> Teil des Massenimports.
        </p>
      </div>

      <div className="flex justify-between">
        <Button variant="secondary" onClick={onZurueck}>← Zurück</Button>
        <Button onClick={onWeiter} disabled={loading}>
          {loading ? 'Wird importiert…' : `${summary.objekte} Objekte jetzt importieren`}
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schritt 5 — Ergebnis
// ---------------------------------------------------------------------------
function Schritt5({ result }: { result: CommitResponse }) {
  const ok          = result.ergebnisse.filter(e => e.status === 'ok')
  const fehler      = result.ergebnisse.filter(e => e.status === 'fehler')
  const uebersprungen = result.ergebnisse.filter(e => e.status === 'uebersprungen')

  const downloadFehlerCsv = () => {
    const rows = fehler.map(e => `${e.zeilennummer};"${e.bezeichnung ?? ''}";${e.meldung ?? ''}`)
    const csv  = ['Zeile;Bezeichnung;Fehler', ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = 'massenimport_fehler.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className={`rounded-xl border p-5 ${
        result.status === 'committed' ? 'bg-green-50 border-green-200' :
        result.status === 'partial'   ? 'bg-yellow-50 border-yellow-200' :
                                        'bg-red-50 border-red-200'
      }`}>
        <h3 className="font-bold text-lg mb-1">
          {result.status === 'committed' ? '✓ Import abgeschlossen' :
           result.status === 'partial'   ? '⚠ Import teilweise abgeschlossen' :
                                           '✗ Import fehlgeschlagen'}
        </h3>
        <p className="text-sm">
          {result.importiert} Objekte erfolgreich importiert
          {result.fehler > 0 ? `, ${result.fehler} fehlgeschlagen` : ''}.
        </p>
      </div>

      {/* Erfolgreich angelegt */}
      {ok.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Angelegte Objekte</h4>
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Zeile</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Bezeichnung</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Aktion</th>
                </tr>
              </thead>
              <tbody>
                {ok.map(e => (
                  <tr key={e.zeilennummer} className="border-t">
                    <td className="px-4 py-2 text-gray-400 font-mono text-xs">{e.zeilennummer}</td>
                    <td className="px-4 py-2 text-gray-800">{e.bezeichnung}</td>
                    <td className="px-4 py-2">
                      <Link
                        to={`/objekte/${e.objekt_id}`}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        Objekt öffnen →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Fehler + Download */}
      {fehler.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-red-700">Fehlgeschlagene Zeilen</h4>
            <button
              onClick={downloadFehlerCsv}
              className="text-xs text-primary-600 hover:underline"
            >
              CSV herunterladen
            </button>
          </div>
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Zeile</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Bezeichnung</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Fehler</th>
                </tr>
              </thead>
              <tbody>
                {fehler.map(e => (
                  <tr key={e.zeilennummer} className="border-t">
                    <td className="px-4 py-2 text-gray-400 font-mono text-xs">{e.zeilennummer}</td>
                    <td className="px-4 py-2 text-gray-600">{e.bezeichnung ?? '—'}</td>
                    <td className="px-4 py-2 text-red-600 text-xs">{e.meldung}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {uebersprungen.length > 0 && (
        <p className="text-xs text-gray-400">
          {uebersprungen.length} Zeile(n) wurden wegen Validierungsfehlern übersprungen.
        </p>
      )}

      <div className="flex gap-3 pt-2">
        <Link to="/objekte">
          <Button>Zur Objektliste →</Button>
        </Link>
        <Link to="/massenimport/weg">
          <Button variant="secondary">Neuen Import starten</Button>
        </Link>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------
type Schritt = 1 | 2 | 3 | 4 | 5

export function MassenimportWEG() {
  const [schritt, setSchritt]   = useState<Schritt>(1)
  const [preview, setPreview]   = useState<PreviewResponse | null>(null)
  const [result, setResult]     = useState<CommitResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const SCHRITTE = ['Vorlage', 'Upload', 'Vorschau', 'Bestätigung', 'Ergebnis']

  const handleUpload = async (file: File) => {
    setUploading(true)
    setUploadError(null)
    try {
      const data = await massenimportApi.preview(file)
      setPreview(data)
      setSchritt(3)
    } catch (e: any) {
      setUploadError(e?.response?.data?.error ?? 'Unbekannter Fehler beim Hochladen.')
    } finally {
      setUploading(false)
    }
  }

  const handleCommit = async () => {
    if (!preview) return
    setCommitting(true)
    try {
      const data = await massenimportApi.commit(preview.preview_token)
      setResult(data)
      setSchritt(5)
    } catch (e: any) {
      alert(e?.response?.data?.error ?? 'Fehler beim Import.')
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/" className="text-primary-600 hover:underline text-sm">← Dashboard</Link>
        <span className="text-gray-300">|</span>
        <h1 className="text-2xl font-bold text-gray-900">Massenimport WEG-Objekte</h1>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-0 mb-8">
        {SCHRITTE.map((label, idx) => {
          const nr   = (idx + 1) as Schritt
          const done = schritt > nr
          const active = schritt === nr
          return (
            <div key={nr} className="flex items-center flex-1">
              <div className={`flex items-center gap-2 ${active ? 'text-primary-700' : done ? 'text-green-600' : 'text-gray-400'}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 flex-shrink-0 ${
                  active ? 'border-primary-600 bg-primary-600 text-white' :
                  done   ? 'border-green-500 bg-green-500 text-white' :
                           'border-gray-300 bg-white text-gray-400'
                }`}>
                  {done ? '✓' : nr}
                </div>
                <span className="text-xs font-medium hidden sm:inline">{label}</span>
              </div>
              {idx < SCHRITTE.length - 1 && (
                <div className={`flex-1 h-0.5 mx-2 ${done ? 'bg-green-400' : 'bg-gray-200'}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Inhalt */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-4xl">
        {schritt === 1 && <Schritt1 onWeiter={() => setSchritt(2)} />}

        {schritt === 2 && (
          <div className="space-y-4">
            <Schritt2 onWeiter={handleUpload} />
            {uploading && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                Datei wird geprüft…
              </div>
            )}
            {uploadError && (
              <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
                {uploadError}
              </div>
            )}
          </div>
        )}

        {schritt === 3 && preview && (
          <Schritt3
            preview={preview}
            onWeiter={() => setSchritt(4)}
            onZurueck={() => { setSchritt(2); setPreview(null) }}
          />
        )}

        {schritt === 4 && preview && (
          <Schritt4
            preview={preview}
            onWeiter={handleCommit}
            onZurueck={() => setSchritt(3)}
            loading={committing}
          />
        )}

        {schritt === 5 && result && <Schritt5 result={result} />}
      </div>
    </div>
  )
}
