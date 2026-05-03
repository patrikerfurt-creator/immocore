import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { buchhaltungApi } from '../api/buchhaltung'
import { rechnungenApi, type FreigabeLimit } from '../api/rechnungen'
import { Button } from '../components/ui/Button'
import type { CamtImportEinstellung, CamtImportLog } from '../types'

type Tab = 'ebanking' | 'rechnungen' | 'dokumente' | 'freigabelimits'

// ---------------------------------------------------------------------------
// Hilfsfunktion: generische Ordner-Einstellungsmaske
// ---------------------------------------------------------------------------

type ImportResult = { importiert: number; duplikate?: number; prueffaelle?: number; fehler: number; dateien: number }

function OrdnerMaske({ bereich }: { bereich: 'rechnungen' | 'dokumente' }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)

  const { data: einstellung } = useQuery({
    queryKey: ['import-ordner', bereich],
    queryFn: () => buchhaltungApi.importOrdnerEinstellung(bereich),
  })

  const speichernMut = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      buchhaltungApi.importOrdnerSpeichern(
        (einstellung as Record<string, string> | null)?.id ?? null,
        { ...data, bereich }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['import-ordner', bereich] })
      setForm({})
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const importMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.importOrdnerJetztImportieren(id),
    onSuccess: (r) => setImportResult(r as ImportResult),
  })

  const merged: Record<string, string> = { ...((einstellung as Record<string, string>) ?? {}), ...form }
  const felder = bereich === 'dokumente'
    ? [
        { key: 'import_ordner', label: 'Import-Ordner' },
        { key: 'archiv_ordner', label: 'Archiv-Ordner' },
      ]
    : [
        { key: 'import_ordner', label: 'Import-Ordner' },
        { key: 'archiv_ordner', label: 'Archiv-Ordner' },
        { key: 'fehler_ordner', label: 'Fehler-Ordner' },
      ]

  const einstellungId = (einstellung as Record<string, string> | null)?.id ?? null

  return (
    <div className="space-y-4">
      {felder.map(({ key, label }) => (
        <div key={key}>
          <label className="block text-sm text-gray-600 mb-1">{label}</label>
          <input
            type="text"
            placeholder="/app/ordner oder C:\Pfad\zum\Ordner"
            value={merged[key] ?? ''}
            onChange={e => setForm(prev => ({ ...prev, [key]: e.target.value }))}
            className="border rounded px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      ))}

      <div className="border-t pt-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-3">Automatischer Import</div>
        <div className="text-sm text-gray-600 bg-gray-50 rounded px-3 py-2 mb-3">
          Celery Beat scannt den Import-Ordner automatisch alle <strong>5 Minuten</strong>.
        </div>

        {importResult && (
          <div className="text-sm p-3 rounded bg-blue-50 border border-blue-200 text-blue-800 mb-3">
            <span className="font-medium">Import abgeschlossen:</span>{' '}
            {importResult.dateien === 0
              ? 'Keine neuen Dateien im Ordner.'
              : `${importResult.importiert} importiert · ${importResult.duplikate ?? 0} Duplikate · ${importResult.fehler} Fehler`}
            {(importResult.prueffaelle ?? 0) > 0 && (
              <span className="ml-2 text-amber-700">· {importResult.prueffaelle} Prüffälle</span>
            )}
          </div>
        )}

        {saved && (
          <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 mb-3">
            Einstellungen gespeichert.
          </div>
        )}
        {speichernMut.isError && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-3">
            Fehler beim Speichern.
          </div>
        )}

        <div className="flex gap-3 flex-wrap">
          <Button
            onClick={() => speichernMut.mutate(form)}
            disabled={speichernMut.isPending || Object.keys(form).length === 0}
          >
            {speichernMut.isPending ? 'Speichere…' : 'Speichern'}
          </Button>
          {einstellungId && (
            <Button
              variant="secondary"
              onClick={() => { setImportResult(null); importMut.mutate(einstellungId) }}
              disabled={importMut.isPending}
            >
              {importMut.isPending ? 'Importiere…' : 'Jetzt importieren'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// E-Banking-Einstellungsmaske (aus EBanking.tsx extrahiert)
// ---------------------------------------------------------------------------

function EBankingEinstellungen() {
  const qc = useQueryClient()
  const [einst, setEinst] = useState<Partial<CamtImportEinstellung>>({})
  const [testResult, setTestResult] = useState<{ ok: boolean; fehler?: string } | null>(null)
  const [importResult, setImportResult] = useState<{
    importiert: number; duplikate: number; erkannt: number; fehler: number; dateien: number
  } | null>(null)

  const { data: einstellung } = useQuery({
    queryKey: ['camt-einstellung'],
    queryFn: () => buchhaltungApi.camtEinstellung(),
  })

  const speichernMut = useMutation({
    mutationFn: (data: Partial<CamtImportEinstellung>) =>
      buchhaltungApi.camtEinstellungSpeichern(einstellung?.id ?? null, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['camt-einstellung'] })
      setEinst({})
    },
  })

  const testMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.camtVerbindungTesten(id),
    onSuccess: (r) => setTestResult(r),
    onError: () => setTestResult({ ok: false, fehler: 'Netzwerkfehler' }),
  })

  const importMut = useMutation({
    mutationFn: (id: string) => buchhaltungApi.camtJetztImportieren(id),
    onSuccess: (r) => {
      setImportResult(r)
      qc.invalidateQueries({ queryKey: ['kontoumsaetze'] })
    },
    onError: () => setImportResult(null),
  })

  async function handleVerbindungTesten() {
    if (!einstellung?.id) return
    setTestResult(null)
    if (Object.keys(einst).length > 0) {
      await speichernMut.mutateAsync(einst)
    }
    testMut.mutate(einstellung.id)
  }

  const aktuelleEinst: Partial<CamtImportEinstellung> = { ...einstellung, ...einst }

  return (
    <div className="space-y-4">
      {[
        { key: 'import_ordner', label: 'Import-Ordner' },
        { key: 'archiv_ordner', label: 'Archiv-Ordner' },
        { key: 'fehler_ordner', label: 'Fehler-Ordner' },
      ].map(({ key, label }) => (
        <div key={key}>
          <label className="block text-sm text-gray-600 mb-1">{label}</label>
          <input
            type="text"
            placeholder="/app/camt_dat"
            value={(aktuelleEinst as Record<string, string>)[key] ?? ''}
            onChange={e => setEinst(prev => ({ ...prev, [key]: e.target.value }))}
            className="border rounded px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      ))}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Poll-Intervall (Sek.)</label>
          <input
            type="number"
            value={aktuelleEinst.poll_intervall_sek ?? 7200}
            onChange={e => setEinst(prev => ({ ...prev, poll_intervall_sek: Number(e.target.value) }))}
            className="border rounded px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Dateimuster</label>
          <input
            type="text"
            value={aktuelleEinst.datei_muster ?? '*.xml,*.camt'}
            onChange={e => setEinst(prev => ({ ...prev, datei_muster: e.target.value }))}
            className="border rounded px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {einstellung?.letzter_import_am && (
        <div className="text-xs text-gray-400">
          Letzter Import: {new Date(einstellung.letzter_import_am).toLocaleString('de-DE')}
          {einstellung.letzter_import_datei && ` · ${einstellung.letzter_import_datei}`}
        </div>
      )}

      {Object.keys(einst).length > 0 && (
        <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          Ungespeicherte Änderungen — werden beim Verbindungstest automatisch gespeichert.
        </div>
      )}

      {testResult && (
        <div className={`text-sm p-2 rounded ${testResult.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {testResult.ok ? 'Verbindung erfolgreich — Ordner zugänglich' : `Fehler: ${testResult.fehler}`}
        </div>
      )}

      {importResult && (
        <div className="text-sm p-3 rounded bg-blue-50 border border-blue-200 text-blue-800">
          <span className="font-medium">Import abgeschlossen:</span>{' '}
          {importResult.dateien === 0
            ? 'Keine neuen Dateien im Ordner.'
            : `${importResult.importiert} importiert · ${importResult.duplikate} Duplikate · ${importResult.erkannt} erkannt`}
          {importResult.fehler > 0 && <span className="text-red-600 ml-2">· {importResult.fehler} Fehler</span>}
        </div>
      )}

      <div className="border-t pt-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-3">Automatischer Import</div>
        <div className="text-sm text-gray-600 bg-gray-50 rounded px-3 py-2 mb-3">
          Celery Beat scannt den Import-Ordner automatisch alle <strong>2 Stunden</strong>.
        </div>
        <div className="flex gap-3 flex-wrap">
          <Button
            onClick={() => speichernMut.mutate(einst)}
            disabled={speichernMut.isPending}
          >
            {speichernMut.isPending ? 'Speichere…' : 'Speichern'}
          </Button>
          {einstellung?.id && (
            <>
              <Button variant="secondary" onClick={handleVerbindungTesten} disabled={testMut.isPending || speichernMut.isPending}>
                {testMut.isPending ? 'Prüfe…' : 'Verbindung testen'}
              </Button>
              <Button
                variant="secondary"
                onClick={() => { setImportResult(null); importMut.mutate(einstellung.id) }}
                disabled={importMut.isPending}
              >
                {importMut.isPending ? 'Importiere…' : 'Jetzt importieren'}
              </Button>
            </>
          )}
        </div>
      </div>

      <CamtImportLogTabelle />
    </div>
  )
}

function CamtImportLogTabelle() {
  const { data: logs, isLoading } = useQuery({
    queryKey: ['camt-logs'],
    queryFn: () => buchhaltungApi.camtLogs(20),
  })

  if (isLoading) return <div className="mt-6 text-sm text-gray-400">Lade Importprotokoll…</div>

  return (
    <div className="mt-6 border-t pt-5">
      <div className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-3">Importprotokoll</div>
      {(!logs || logs.length === 0) ? (
        <p className="text-sm text-gray-400">Noch keine Importläufe vorhanden.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Zeitpunkt</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Dateien</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Importiert</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Duplikate</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Erkannt</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Fehler</th>
              </tr>
            </thead>
            <tbody>
              {(logs as CamtImportLog[]).map(log => (
                <>
                  <tr key={log.id} className={`border-t ${log.anzahl_fehler > 0 ? 'bg-red-50' : ''}`}>
                    <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                      {new Date(log.zeitpunkt).toLocaleString('de-DE')}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-gray-600">{log.anzahl_dateien}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-green-700 font-medium">{log.anzahl_importiert}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-gray-400">{log.anzahl_duplikate}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-blue-600">{log.anzahl_erkannt}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {log.anzahl_fehler > 0
                        ? <span className="text-red-600 font-semibold">{log.anzahl_fehler}</span>
                        : <span className="text-gray-300">—</span>}
                    </td>
                  </tr>
                  {log.fehler_details.length > 0 && log.fehler_details.map((f, i) => (
                    <tr key={`${log.id}-err-${i}`} className="bg-red-50 border-t border-red-100">
                      <td colSpan={6} className="px-3 py-1.5 text-xs text-red-700">
                        <span className="font-medium">{f.datei}</span>
                        <span className="text-red-500 ml-2">→ {f.meldung}</span>
                      </td>
                    </tr>
                  ))}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Globale Freigabelimits
// ---------------------------------------------------------------------------

const ROLLEN_FREIGABE = [
  { value: 'auto',              label: 'Automatisch (keine Freigabe)' },
  { value: 'objektmanager',    label: 'Objektmanager' },
  { value: 'sachbearbeiter',   label: 'Sachbearbeiter' },
  { value: 'geschaeftsfuehrer', label: 'Geschäftsführer' },
]

function GlobaleFreigabelimitsEinstellung() {
  const qc = useQueryClient()
  const [stufen, setStufen] = useState<FreigabeLimit[] | null>(null)
  const [saved, setSaved] = useState(false)

  const { data: gespeichert, isLoading } = useQuery({
    queryKey: ['freigabelimits-standard'],
    queryFn: () => rechnungenApi.freigabelimitStandard(),
  })

  const aktuell: FreigabeLimit[] = stufen ?? gespeichert ?? []

  const update = (idx: number, field: keyof FreigabeLimit, value: unknown) => {
    const basis = stufen ?? gespeichert ?? []
    setStufen(basis.map((s, i) => i === idx ? { ...s, [field]: value } : s))
    setSaved(false)
  }

  const speichernMut = useMutation({
    mutationFn: (grenzen: FreigabeLimit[]) => rechnungenApi.freigabelimitStandardSpeichern(grenzen),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['freigabelimits-standard'] })
      setStufen(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const addStufe = () => {
    const basis = stufen ?? gespeichert ?? []
    setStufen([...basis, { bis: null, rolle: 'geschaeftsfuehrer', frist_tage: 5, beschreibung: '' }])
    setSaved(false)
  }

  const removeStufe = (idx: number) => {
    const basis = stufen ?? gespeichert ?? []
    setStufen(basis.filter((_, i) => i !== idx))
    setSaved(false)
  }

  if (isLoading) return <p className="text-sm text-gray-400">Lade…</p>

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Diese Standardwerte gelten für alle neuen Objekte. Individuelle Anpassungen sind in der jeweiligen Objekt-Detailseite möglich.
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm min-w-[580px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-600 w-10">Stufe</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Bis (€)</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Freigabe durch</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Frist (Tage)</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Beschreibung</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {aktuell.map((s, idx) => (
              <tr key={idx} className="border-t border-gray-100 hover:bg-gray-50">
                <td className="px-3 py-2 text-gray-500 font-medium">{idx + 1}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={s.bis ?? ''}
                      onChange={e => update(idx, 'bis', e.target.value ? parseFloat(e.target.value) : null)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:border-blue-500 w-[100px]"
                      placeholder={idx === aktuell.length - 1 ? '∞' : '0'}
                      min={0}
                    />
                    {idx === aktuell.length - 1 && (
                      <span className="text-xs text-gray-400">(leer = unbegrenzt)</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <select
                    value={s.rolle}
                    onChange={e => update(idx, 'rolle', e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:border-blue-500"
                  >
                    {ROLLEN_FREIGABE.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <input
                    type="number"
                    value={s.frist_tage}
                    onChange={e => update(idx, 'frist_tage', parseInt(e.target.value) || 0)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:border-blue-500 w-[70px]"
                    min={0}
                  />
                </td>
                <td className="px-3 py-2">
                  <input
                    type="text"
                    value={s.beschreibung}
                    onChange={e => update(idx, 'beschreibung', e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:border-blue-500 w-full"
                  />
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => removeStufe(idx)} className="text-red-400 hover:text-red-600 text-xs">✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={addStufe}
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          + Stufe hinzufügen
        </button>
        <Button
          onClick={() => speichernMut.mutate(aktuell)}
          disabled={speichernMut.isPending}
        >
          {speichernMut.isPending ? 'Speichere…' : 'Speichern'}
        </Button>
      </div>

      {saved && (
        <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
          Freigabelimits gespeichert.
        </div>
      )}
      {speichernMut.isError && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          Fehler beim Speichern.
        </div>
      )}

      <div className="rounded-md bg-blue-50 border border-blue-100 p-3">
        <p className="text-xs text-blue-700">
          <strong>Hinweis:</strong> Frist 0 Tage = Sofortfreigabe. Die letzte Stufe ohne Betragslimit gilt für alle Beträge darüber.
          Individuelle Anpassungen je Objekt erfolgen in der Objekt-Detailseite.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptseite
// ---------------------------------------------------------------------------

export function Einstellungen() {
  const [tab, setTab] = useState<Tab>('ebanking')

  const tabs: { id: Tab; label: string }[] = [
    { id: 'ebanking', label: 'E-Banking' },
    { id: 'rechnungen', label: 'Rechnungen' },
    { id: 'dokumente', label: 'Dokumente' },
    { id: 'freigabelimits', label: 'Freigabelimits' },
  ]

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Einstellungen</h1>

      <div className="border-b mb-6 flex gap-6">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`pb-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border shadow-sm p-6">
        {tab === 'ebanking' && (
          <>
            <h2 className="font-semibold text-gray-800 mb-4">CAMT-Import-Konfiguration</h2>
            <EBankingEinstellungen />
          </>
        )}
        {tab === 'rechnungen' && (
          <>
            <h2 className="font-semibold text-gray-800 mb-1">Rechnungseingang-Ordner</h2>
            <p className="text-sm text-gray-500 mb-4">
              PDFs und Bilder in diesem Ordner werden automatisch per OCR eingelesen.
            </p>
            <OrdnerMaske bereich="rechnungen" />
          </>
        )}
        {tab === 'dokumente' && (
          <>
            <h2 className="font-semibold text-gray-800 mb-1">Dokumente-Eingangsordner</h2>
            <p className="text-sm text-gray-500 mb-4">
              Dokumente in diesem Ordner werden automatisch importiert.
            </p>
            <OrdnerMaske bereich="dokumente" />
          </>
        )}
        {tab === 'freigabelimits' && (
          <>
            <h2 className="font-semibold text-gray-800 mb-1">Freigabelimits (Standard)</h2>
            <p className="text-sm text-gray-500 mb-4">
              Standardwerte für die Rechnungsfreigabe — werden für alle neuen Objekte verwendet.
            </p>
            <GlobaleFreigabelimitsEinstellung />
          </>
        )}
      </div>
    </div>
  )
}
