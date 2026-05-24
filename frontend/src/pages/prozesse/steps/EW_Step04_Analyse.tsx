import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../../components/ui/Button'
import { prozesseApi } from '../../../api/prozesse'
import type { WechselAnalyseSollstellung } from '../../../types'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

function fmtEur(s: string): string {
  const n = parseFloat(s)
  return isNaN(n) ? s : n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

export function EW_Step04_Analyse({ prozessId, stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const step1 = (stepsData['1'] ?? {}) as Record<string, unknown>
  const art = step1.art as string | undefined

  const { data: analyse, isLoading: analyseLoading, error: analyseError } = useQuery({
    queryKey: ['ew-analyse', prozessId],
    queryFn: () => prozesseApi.ewAnalyse(prozessId),
    enabled: art === 'rueckwirkend',
    staleTime: 30_000,
  })

  // Checkbox state for stornieren
  const [storniereChecked, setStorniereChecked] = useState<Record<string, boolean>>(() => {
    const saved = (initialData.stornieren_ids as string[] | undefined) ?? []
    const fromAnalyse = analyse?.stornieren ?? []
    if (saved.length > 0) {
      return Object.fromEntries(fromAnalyse.map(s => [s.sollstellung_id, saved.includes(s.sollstellung_id)]))
    }
    return Object.fromEntries((analyse?.stornieren ?? []).map(s => [s.sollstellung_id, true]))
  })

  // Checkbox state for erstatten
  const [erstatteChecked, setErstatteChecked] = useState<Record<string, boolean>>(() => {
    const saved = (initialData.erstatten as Array<{ss_id:string}> | undefined) ?? []
    if (saved.length > 0) {
      const savedIds = saved.map(s => s.ss_id)
      return Object.fromEntries((analyse?.erstatten ?? []).map(s => [s.sollstellung_id, savedIds.includes(s.sollstellung_id)]))
    }
    return Object.fromEntries((analyse?.erstatten ?? []).map(s => [s.sollstellung_id, true]))
  })

  const [verkaeuferIban, setVerkaeuferIban] = useState<string>((initialData.verkaeufer_iban as string) ?? analyse?.verkaeufer_iban ?? '')

  // Update defaults when analyse loads
  React.useEffect(() => {
    if (!analyse) return
    setStorniereChecked(prev => {
      const next = { ...prev }
      for (const ss of analyse.stornieren) {
        if (!(ss.sollstellung_id in next)) next[ss.sollstellung_id] = true
      }
      return next
    })
    setErstatteChecked(prev => {
      const next = { ...prev }
      for (const ss of analyse.erstatten) {
        if (!(ss.sollstellung_id in next)) next[ss.sollstellung_id] = true
      }
      return next
    })
    if (!verkaeuferIban && analyse.verkaeufer_iban) setVerkaeuferIban(analyse.verkaeufer_iban)
  }, [analyse])

  const erstattungSumme = analyse?.erstatten
    .filter(s => erstatteChecked[s.sollstellung_id])
    .reduce((acc, s) => acc + parseFloat(s.ist_betrag), 0) ?? 0

  const hatErstattung = analyse?.erstatten.some(s => erstatteChecked[s.sollstellung_id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (art !== 'rueckwirkend') {
      await onWeiter({ stornieren_ids: [], erstatten: [], verkaeufer_iban: null })
      return
    }
    const storniereIds = Object.entries(storniereChecked).filter(([, v]) => v).map(([k]) => k)
    const erstattePositionen = (analyse?.erstatten ?? [])
      .filter(s => erstatteChecked[s.sollstellung_id])
      .map(s => ({ ss_id: s.sollstellung_id, ist_betrag: s.ist_betrag }))
    await onWeiter({
      stornieren_ids: storniereIds,
      erstatten: erstattePositionen,
      verkaeufer_iban: hatErstattung ? verkaeuferIban : null,
    })
  }

  if (art !== 'rueckwirkend') {
    return (
      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="rounded-md bg-blue-50 border border-blue-200 p-4 text-sm text-blue-800">
          <p className="font-medium">Zukünftiger Wechsel — kein Korrekturschritt nötig.</p>
          <p className="mt-1">Da der Stichtag in der Zukunft liegt, gibt es keine zu stornierenden Verkäufer-Sollstellungen.</p>
        </div>
        {errors.length > 0 && (
          <div className="rounded-md bg-red-50 p-3 space-y-1">
            {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
          </div>
        )}
        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={isLoading}>{isLoading ? 'Speichern…' : 'Weiter'}</Button>
        </div>
      </form>
    )
  }

  if (analyseLoading) return <p className="text-sm text-gray-400">Lade Analyse…</p>
  if (analyseError) return <p className="text-sm text-red-600">Fehler beim Laden der Analyse.</p>

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {analyse?.warnung_keine_iban && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          ⚠ Beim Verkäufer ist keine IBAN hinterlegt. Bitte am Personenstammdatensatz ergänzen, bevor Erstattungen möglich sind.
        </div>
      )}

      {/* Tabelle 4a: Stornieren */}
      {analyse && analyse.stornieren.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Zu stornierende Sollstellungen (ist_betrag = 0)</h4>
          <div className="rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-8">✓</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">OPOS-Nr.</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Periode</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Soll</th>
                </tr>
              </thead>
              <tbody>
                {analyse.stornieren.map((ss: WechselAnalyseSollstellung) => (
                  <tr key={ss.sollstellung_id} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={storniereChecked[ss.sollstellung_id] ?? true}
                        onChange={e => setStorniereChecked(prev => ({ ...prev, [ss.sollstellung_id]: e.target.checked }))} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-gray-600">{ss.opos_nr}</td>
                    <td className="px-3 py-2">{fmtDate(ss.periode)}</td>
                    <td className="px-3 py-2 text-right">{fmtEur(ss.soll_betrag)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tabelle 4b: Erstatten */}
      {analyse && analyse.erstatten.length > 0 && (
        <div>
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800 mb-3">
            ⚠ Der Verkäufer hat in diesem Zeitraum bereits Hausgeld bezahlt. Das System wird eine SEPA-Überweisung an die hinterlegte IBAN des Verkäufers vorbereiten. Stelle sicher, dass die Verkäufer-IBAN noch aktiv ist.
          </div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">An Verkäufer rückerstatten</h4>
          <div className="rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-8">✓</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">OPOS-Nr.</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Periode</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Soll</th>
                  <th className="px-3 py-2 text-right font-medium text-gray-600">Ist (= Erstattung)</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600"></th>
                </tr>
              </thead>
              <tbody>
                {analyse.erstatten.map((ss: WechselAnalyseSollstellung) => (
                  <tr key={ss.sollstellung_id} className="border-b border-gray-100 last:border-0">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={erstatteChecked[ss.sollstellung_id] ?? true}
                        onChange={e => setErstatteChecked(prev => ({ ...prev, [ss.sollstellung_id]: e.target.checked }))} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-gray-600">{ss.opos_nr}</td>
                    <td className="px-3 py-2">{fmtDate(ss.periode)}</td>
                    <td className="px-3 py-2 text-right text-gray-400">{fmtEur(ss.soll_betrag)}</td>
                    <td className="px-3 py-2 text-right font-medium">{fmtEur(ss.ist_betrag)}</td>
                    <td className="px-3 py-2">
                      {ss.lastschrift_juenger_56_tage && (
                        <span className="text-xs text-amber-600" title="Diese Zahlung wurde vor weniger als 8 Wochen per Lastschrift eingezogen">⚠ &lt;8 Wo.</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50 border-t border-gray-200">
                <tr>
                  <td colSpan={4} className="px-3 py-2 text-sm font-medium text-gray-700">Summe Erstattung</td>
                  <td className="px-3 py-2 text-right font-bold text-gray-900">
                    {erstattungSumme.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>

          {hatErstattung && (
            <div className="mt-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Verkäufer-IBAN für Überweisung *</label>
              <input type="text" className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={verkaeuferIban} onChange={e => setVerkaeuferIban(e.target.value)}
                placeholder="DE89…" />
            </div>
          )}
        </div>
      )}

      {analyse && analyse.stornieren.length === 0 && analyse.erstatten.length === 0 && (
        <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-700">
          Keine offenen Sollstellungen des Verkäufers im betroffenen Zeitraum — kein Korrekturaufwand.
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || (hatErstattung === true && !verkaeuferIban)}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
