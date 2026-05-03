import React, { useState, useRef } from 'react'
import { Button } from '../../../components/ui/Button'
import { prozesseApi } from '../../../api/prozesse'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

// Typ-Codes: 100=Wohnung, 200=Gewerbe, 900=Stellplatz, 800=Sonstiges
const EINHEIT_TYPEN: { code: string; label: string; dbValue: string }[] = [
  { code: '100', label: '100 – Wohnung',    dbValue: 'Wohnung'    },
  { code: '200', label: '200 – Gewerbe',    dbValue: 'Gewerbe'    },
  { code: '900', label: '900 – Stellplatz', dbValue: 'Stellplatz' },
  { code: '800', label: '800 – Sonstiges',  dbValue: 'Sonstiges'  },
]

function dbValueToCode(dbValue: string): string {
  return EINHEIT_TYPEN.find(t => t.dbValue === dbValue)?.code ?? '100'
}

interface EinheitRow {
  id: string
  wohnungsbezeichnung: string
  flaechennummer: string
  einheit_typ_code: string  // '100' | '200' | '900' | '800'
  lage: string
}

let rowCounter = 1
function makeRowId() { return `einheit-${rowCounter++}` }

function getInitialEinheiten(initialData: Record<string, unknown>): EinheitRow[] {
  if (Array.isArray(initialData.einheiten) && initialData.einheiten.length > 0) {
    return (initialData.einheiten as Record<string, string>[]).map(e => ({
      id: (e.id as string) ?? makeRowId(),
      wohnungsbezeichnung: e.wohnungsbezeichnung ?? e.einheit_nr ?? '',
      flaechennummer: e.flaechennummer ?? '',
      einheit_typ_code: e.einheit_typ_code ?? dbValueToCode(e.einheit_typ ?? ''),
      lage: e.lage ?? '',
    }))
  }
  return [{ id: makeRowId(), wohnungsbezeichnung: '', flaechennummer: '', einheit_typ_code: '100', lage: '' }]
}

export function Step04_Einheiten({ prozessId, initialData, onWeiter, isLoading, errors }: StepProps) {
  const [mode, setMode] = useState<'manuell' | 'csv'>((initialData.mode as 'manuell' | 'csv') ?? 'manuell')
  const [einheiten, setEinheiten] = useState<EinheitRow[]>(() => getInitialEinheiten(initialData))
  const [csvPreview, setCsvPreview] = useState<EinheitRow[]>((initialData.csv_preview as EinheitRow[]) ?? [])
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvUploading, setCsvUploading] = useState(false)
  const [csvError, setCsvError] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const update = (id: string, field: keyof EinheitRow, value: string) => {
    setEinheiten(prev => prev.map(e => e.id === id ? { ...e, [field]: value } : e))
  }

  const addRow = () => {
    setEinheiten(prev => [...prev, { id: makeRowId(), wohnungsbezeichnung: '', flaechennummer: '', einheit_typ_code: '100', lage: '' }])
  }

  const removeRow = (id: string) => {
    setEinheiten(prev => prev.filter(e => e.id !== id))
  }

  const downloadVorlage = async () => {
    try {
      const blob = await prozesseApi.csvVorlageEinheiten(prozessId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'einheiten_vorlage.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // ignore
    }
  }

  const handleFileUpload = async (file: File) => {
    setCsvFile(file)
    setCsvError(null)
    setCsvUploading(true)
    try {
      const result = await prozesseApi.csvUploadEinheiten(prozessId, file)
      if (result.errors?.length) {
        setCsvError(result.errors.join('\n'))
      }
      setCsvPreview(result.einheiten ?? result.rows ?? [])
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCsvError(msg ?? 'CSV-Upload fehlgeschlagen.')
    } finally {
      setCsvUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (mode === 'manuell') {
      await onWeiter({
        mode: 'manuell',
        einheiten: einheiten.map(({ id: _id, einheit_typ_code, ...rest }) => ({
          wohnungsbezeichnung: rest.wohnungsbezeichnung,
          flaechennummer: rest.flaechennummer,
          einheit_typ: EINHEIT_TYPEN.find(t => t.code === einheit_typ_code)?.dbValue ?? 'Wohnung',
          einheit_typ_code,
          lage: rest.lage,
        })),
      })
    } else {
      await onWeiter({ mode: 'csv', csv_preview: csvPreview, einheiten: csvPreview })
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Mode toggle */}
      <div className="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
        {(['manuell', 'csv'] as const).map(m => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
              mode === m ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {m === 'manuell' ? 'Manuell' : 'CSV-Import'}
          </button>
        ))}
      </div>

      {mode === 'manuell' && (
        <div className="space-y-3">
          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm min-w-[500px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Bez. Einheit *</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Flächennummer</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Typ *</th>
                  <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Lage</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {einheiten.map(e => (
                  <tr key={e.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={e.wohnungsbezeichnung}
                        onChange={ev => update(e.id, 'wohnungsbezeichnung', ev.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                        placeholder="WE01"
                        required
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={e.flaechennummer}
                        onChange={ev => update(e.id, 'flaechennummer', ev.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                        placeholder="F01"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={e.einheit_typ_code}
                        onChange={ev => update(e.id, 'einheit_typ_code', ev.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                      >
                        {EINHEIT_TYPEN.map(t => (
                          <option key={t.code} value={t.code}>{t.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={e.lage}
                        onChange={ev => update(e.id, 'lage', ev.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                        placeholder="EG links"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => removeRow(e.id)}
                        disabled={einheiten.length === 1}
                        className="text-gray-300 hover:text-red-500 disabled:opacity-20 transition-colors text-lg leading-none"
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            type="button"
            onClick={addRow}
            className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            <span className="text-base leading-none">+</span> Zeile hinzufügen
          </button>
        </div>
      )}

      {mode === 'csv' && (
        <div className="space-y-4">
          <Button type="button" variant="secondary" size="sm" onClick={downloadVorlage}>
            CSV-Vorlage herunterladen
          </Button>

          {/* Drag & Drop area */}
          <div
            onDragOver={e => { e.preventDefault(); setIsDragOver(true) }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              isDragOver ? 'border-primary-400 bg-primary-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={e => { if (e.target.files?.[0]) handleFileUpload(e.target.files[0]) }}
            />
            <p className="text-sm text-gray-600">
              {csvFile ? csvFile.name : 'CSV-Datei hier ablegen oder klicken zum Auswählen'}
            </p>
            <p className="text-xs text-gray-400 mt-1">Nur .csv-Dateien</p>
          </div>

          {csvUploading && <p className="text-sm text-gray-500">Lade hoch…</p>}
          {csvError && <p className="text-sm text-red-600">{csvError}</p>}

          {csvPreview.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {Object.keys(csvPreview[0]).map(k => (
                      <th key={k} className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {csvPreview.map((row, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-3 py-2 text-gray-700">{String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || csvUploading}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
