import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { buchhaltungApi } from '../../api/buchhaltung'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { useObjektStore } from '../../stores/objekt'
import type { Kontoumsatz, OffenerPosten, Buchungsart, Konto } from '../../types'

const STATUS_FARBE: Record<string, 'green' | 'yellow' | 'red' | 'gray' | 'blue'> = {
  importiert: 'gray',
  erkannt: 'yellow',
  manuell: 'blue',
  gebucht: 'green',
  ignoriert: 'red',
}

const EUR = (v: number | string) =>
  Number(v).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

const DATUM = (s: string) => new Date(s).toLocaleDateString('de-DE')

// ---------------------------------------------------------------------------
// Buchungsmaske (Modal)
// ---------------------------------------------------------------------------

function BuchungsModal({
  umsatz,
  objektId,
  onClose,
  onSuccess,
}: {
  umsatz: Kontoumsatz
  objektId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const istZugang = Number(umsatz.betrag) > 0
  const betrag = Math.abs(Number(umsatz.betrag))

  const [selectedOpos, setSelectedOpos] = useState<Set<string>>(new Set())
  const [sollKontoId, setSollKontoId] = useState('')
  const [buchungsart, setBuchungsart] = useState('')
  const [buchungstext, setBuchungstext] = useState(umsatz.verwendungszweck)

  const { data: buchungsarten } = useQuery({
    queryKey: ['buchungsarten-manuell'],
    queryFn: () => buchhaltungApi.buchungsartenManuell(),
  })

  const { data: opos, isLoading: loadingOpos } = useQuery({
    queryKey: ['offene-posten', objektId, 'offen'],
    queryFn: () => buchhaltungApi.offenePosten({ objekt: objektId, status: 'offen' }),
    enabled: istZugang,
  })

  const { data: konten, isLoading: loadingKonten } = useQuery({
    queryKey: ['konten', objektId],
    queryFn: () => buchhaltungApi.konten(objektId),
    enabled: !istZugang,
  })

  const qc = useQueryClient()
  const buchenMut = useMutation({
    mutationFn: () =>
      buchhaltungApi.umsatzBuchen(umsatz.id, {
        ...(istZugang
          ? { offene_posten_ids: [...selectedOpos] }
          : { soll_konto_id: sollKontoId }),
        buchungsart: buchungsart || undefined,
        buchungstext,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kontoumsaetze'] })
      qc.invalidateQueries({ queryKey: ['offene-posten'] })
      onSuccess()
    },
  })

  const summeSelected = (opos ?? [])
    .filter(op => selectedOpos.has(op.id))
    .reduce((acc, op) => acc + Number(op.betrag_offen), 0)
  const diff = Math.abs(betrag - summeSelected)
  const passt = istZugang ? (diff < 0.01 && selectedOpos.size > 0) : !!sollKontoId

  function toggleOpo(id: string) {
    setSelectedOpos(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b flex justify-between items-start">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Manuell buchen</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {istZugang ? 'Zahlungseingang einem offenen Posten zuordnen' : 'Zahlungsausgang einem Sachkonto zuordnen'}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Transaktionsdetails */}
          <div className={`rounded-lg p-4 space-y-1.5 text-sm ${istZugang ? 'bg-green-50' : 'bg-red-50'}`}>
            <div className="flex justify-between">
              <span className="text-gray-500">Datum</span>
              <span className="font-medium">{DATUM(umsatz.buchungsdatum)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">{istZugang ? 'Auftraggeber' : 'Empfänger'}</span>
              <span className="font-medium">{umsatz.auftraggeber_name || '—'}</span>
            </div>
            {umsatz.auftraggeber_iban && (
              <div className="flex justify-between">
                <span className="text-gray-500">IBAN</span>
                <span className="font-mono text-xs">{umsatz.auftraggeber_iban}</span>
              </div>
            )}
            {umsatz.verwendungszweck && (
              <div className="flex justify-between gap-4">
                <span className="text-gray-500 flex-shrink-0">Verwendungszweck</span>
                <span className="text-right text-gray-700 truncate">{umsatz.verwendungszweck}</span>
              </div>
            )}
            <div className={`flex justify-between pt-1 border-t ${istZugang ? 'border-green-200' : 'border-red-200'}`}>
              <span className="text-gray-500">Betrag</span>
              <span className={`text-lg font-bold ${istZugang ? 'text-green-700' : 'text-red-700'}`}>
                {EUR(umsatz.betrag)}
              </span>
            </div>
          </div>

          {/* Buchungsart */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Buchungsart</label>
            <select
              value={buchungsart}
              onChange={e => setBuchungsart(e.target.value)}
              className="border rounded px-3 py-2 text-sm w-full"
            >
              <option value="">— Buchungsart wählen (optional) —</option>
              {(buchungsarten ?? []).map((ba: Buchungsart) => (
                <option key={ba.id} value={ba.id}>
                  {ba.nr} {ba.kuerzel} — {ba.bezeichnung}
                </option>
              ))}
            </select>
          </div>

          {/* Buchungstext */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Buchungstext</label>
            <input
              type="text"
              value={buchungstext}
              onChange={e => setBuchungstext(e.target.value)}
              className="border rounded px-3 py-2 text-sm w-full"
              placeholder="Buchungstext (optional)"
            />
          </div>

          {/* Zugang: Offene Posten auswählen */}
          {istZugang && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Offene Posten auswählen
              </label>
              {loadingOpos ? (
                <div className="text-sm text-gray-400">Lade offene Posten…</div>
              ) : (opos ?? []).length === 0 ? (
                <div className="text-sm text-gray-400 bg-gray-50 rounded p-3">
                  Keine offenen Posten vorhanden
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b">
                      <tr>
                        <th className="w-10 px-3 py-2" />
                        <th className="text-left px-3 py-2 text-gray-600 font-medium">Eigentümer</th>
                        <th className="text-left px-3 py-2 text-gray-600 font-medium">Einheit</th>
                        <th className="text-left px-3 py-2 text-gray-600 font-medium">Fällig</th>
                        <th className="text-right px-3 py-2 text-gray-600 font-medium">Offen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(opos ?? []).map((op: OffenerPosten) => (
                        <tr
                          key={op.id}
                          onClick={() => toggleOpo(op.id)}
                          className={`border-t cursor-pointer transition-colors ${
                            selectedOpos.has(op.id) ? 'bg-blue-50' : 'hover:bg-gray-50'
                          }`}
                        >
                          <td className="px-3 py-2 text-center">
                            <input type="checkbox" readOnly checked={selectedOpos.has(op.id)} className="rounded" />
                          </td>
                          <td className="px-3 py-2 text-gray-800">{op.eigentuemer_name}</td>
                          <td className="px-3 py-2 text-gray-500">{op.einheit_nr}</td>
                          <td className="px-3 py-2 text-gray-500">{DATUM(op.faellig_ab)}</td>
                          <td className="px-3 py-2 text-right font-semibold tabular-nums">{EUR(op.betrag_offen)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Abgang: Sachkonto auswählen */}
          {!istZugang && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Sachkonto (Soll-Buchung)
              </label>
              {loadingKonten ? (
                <div className="text-sm text-gray-400">Lade Konten…</div>
              ) : (
                <select
                  value={sollKontoId}
                  onChange={e => setSollKontoId(e.target.value)}
                  className="border rounded px-3 py-2 text-sm w-full"
                >
                  <option value="">— Konto wählen —</option>
                  {(konten ?? [])
                    .filter((k: Konto) => k.aktiv && k.kontoart === 'standard')
                    .map((k: Konto) => (
                      <option key={k.id} value={k.id}>
                        {k.kontonummer} — {k.kontoname}
                      </option>
                    ))}
                </select>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t bg-gray-50 rounded-b-xl">
          {istZugang && (
            <div className="text-sm space-y-0.5 mb-3">
              <div className="flex gap-6">
                <span className="text-gray-500">Transaktionsbetrag:</span>
                <span className="font-semibold tabular-nums">{EUR(betrag)}</span>
              </div>
              <div className="flex gap-6">
                <span className="text-gray-500">Summe ausgewählt:</span>
                <span className={`font-semibold tabular-nums ${diff < 0.01 && selectedOpos.size > 0 ? 'text-green-700' : 'text-orange-600'}`}>
                  {EUR(summeSelected)}
                </span>
              </div>
              {diff >= 0.01 && selectedOpos.size > 0 && (
                <div className="text-xs text-orange-600">Differenz: {EUR(diff)}</div>
              )}
              {diff < 0.01 && selectedOpos.size > 0 && (
                <div className="text-xs text-green-600 font-medium">Beträge stimmen überein</div>
              )}
            </div>
          )}

          {buchenMut.isError && (
            <div className="mb-3 text-sm text-red-600 bg-red-50 rounded px-3 py-2">
              {(buchenMut.error as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Fehler beim Buchen'}
            </div>
          )}

          <div className="flex gap-3 justify-end">
            <Button variant="outline" onClick={onClose}>Abbrechen</Button>
            <Button
              onClick={() => buchenMut.mutate()}
              disabled={!passt || buchenMut.isPending}
            >
              {buchenMut.isPending ? 'Buche…' : 'Buchen'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export function EBanking() {
  const objektId = useObjektStore(s => s.selectedId)
  const [statusFilter, setStatusFilter] = useState('')
  const [buchungsUmsatz, setBuchungsUmsatz] = useState<Kontoumsatz | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data: umsaetze, isLoading: loadingUmsaetze } = useQuery({
    queryKey: ['kontoumsaetze', objektId, statusFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (objektId) params.objekt = objektId
      if (statusFilter) params.status = statusFilter
      return buchhaltungApi.kontoumsaetze(params)
    },
    enabled: !!objektId,
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => buchhaltungApi.camtUpload(objektId!, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kontoumsaetze'] })
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadMut.mutate(file)
  }

  if (!objektId) {
    return (
      <div className="p-6 text-gray-500">
        Bitte zuerst ein Objekt in der Seitenleiste auswählen.
      </div>
    )
  }

  return (
    <div>
      {buchungsUmsatz && (
        <BuchungsModal
          umsatz={buchungsUmsatz}
          objektId={objektId}
          onClose={() => setBuchungsUmsatz(null)}
          onSuccess={() => setBuchungsUmsatz(null)}
        />
      )}

      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">E-Banking</h1>
        <div className="flex gap-2">
          <Link
            to="/einstellungen"
            className="text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded px-3 py-1.5 transition-colors"
          >
            ⚙ Einstellungen
          </Link>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xml,.camt"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMut.isPending}
          >
            {uploadMut.isPending ? 'Importiere…' : 'CAMT-Datei importieren'}
          </Button>
        </div>
      </div>

      {uploadMut.isSuccess && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded text-sm text-green-700">
          Import abgeschlossen: {(uploadMut.data as { importiert: number }).importiert} neue,{' '}
          {(uploadMut.data as { duplikate: number }).duplikate} Duplikate,{' '}
          {(uploadMut.data as { erkannt: number }).erkannt} erkannt
        </div>
      )}
      {uploadMut.isError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          Fehler beim Import: {(uploadMut.error as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Unbekannter Fehler'}
        </div>
      )}

      <div className="flex gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="border rounded px-3 py-2 text-sm"
        >
          <option value="">Alle Status</option>
          <option value="importiert">Importiert</option>
          <option value="erkannt">Erkannt</option>
          <option value="manuell">Manuell</option>
          <option value="gebucht">Gebucht</option>
          <option value="ignoriert">Ignoriert</option>
        </select>
      </div>

      {loadingUmsaetze ? (
        <div className="text-gray-500 text-sm">Lade Umsätze…</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-gray-600">Datum</th>
                <th className="text-left px-4 py-3 text-gray-600">Auftraggeber</th>
                <th className="text-left px-4 py-3 text-gray-600">Verwendungszweck</th>
                <th className="text-right px-4 py-3 text-gray-600">Betrag</th>
                <th className="text-left px-4 py-3 text-gray-600">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(umsaetze ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">
                    Keine Umsätze vorhanden
                  </td>
                </tr>
              ) : (umsaetze ?? []).map(u => {
                const kannBuchen = u.status !== 'gebucht' && u.status !== 'ignoriert'
                return (
                  <tr key={u.id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{DATUM(u.buchungsdatum)}</td>
                    <td className="px-4 py-3">
                      <div>{u.auftraggeber_name}</div>
                      <div className="text-gray-400 text-xs">{u.auftraggeber_iban}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{u.verwendungszweck}</td>
                    <td className={`px-4 py-3 text-right font-medium whitespace-nowrap ${Number(u.betrag) >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      {EUR(u.betrag)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={STATUS_FARBE[u.status] ?? 'gray'}>{u.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {kannBuchen && (
                        <button
                          onClick={() => setBuchungsUmsatz(u)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium border border-blue-200 rounded px-2 py-1 hover:bg-blue-50 transition-colors"
                        >
                          Buchen
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
