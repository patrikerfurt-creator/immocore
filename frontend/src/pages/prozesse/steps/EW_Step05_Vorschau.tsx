import React from 'react'
import { Button } from '../../../components/ui/Button'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

function fmtEur(s: string | number | undefined): string {
  if (s === undefined || s === '') return '–'
  const n = typeof s === 'string' ? parseFloat(s) : s
  return isNaN(n) ? String(s) : n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

export function EW_Step05_Vorschau({ stepsData, onWeiter, isLoading, errors }: StepProps) {
  const step1 = (stepsData['1'] ?? {}) as Record<string, unknown>
  const step2 = (stepsData['2'] ?? {}) as Record<string, unknown>
  const step3 = (stepsData['3'] ?? {}) as Record<string, unknown>
  const step4 = (stepsData['4'] ?? {}) as Record<string, unknown>

  const art = step1.art as string
  const hausgeldJeBa = (step3.hausgeld_je_ba ?? {}) as Record<string, string>
  const storniereIds = (step4.stornieren_ids as string[] | undefined) ?? []
  const erstattePositionen = (step4.erstatten as Array<{ss_id: string; ist_betrag: string}> | undefined) ?? []
  const erstattungSumme = erstattePositionen.reduce((acc, p) => acc + parseFloat(p.ist_betrag || '0'), 0)

  const handleBestaetigen = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({})
  }

  return (
    <form onSubmit={handleBestaetigen} className="space-y-6">
      <div className="rounded-lg border border-gray-200 p-5 space-y-4 text-sm font-mono bg-gray-50">
        <p className="text-base font-bold text-gray-800 font-sans mb-2">EIGENTÜMERWECHSEL — VORSCHAU</p>

        <div className="grid grid-cols-2 gap-1 text-xs">
          <span className="text-gray-500">Stichtag:</span>
          <span className="font-medium">{fmtDate(step1.stichtag as string)}</span>
          <span className="text-gray-500">Wirkungsperiode:</span>
          <span className="font-medium">{fmtDate(step1.wirkungs_periode as string)}</span>
          <span className="text-gray-500">Art:</span>
          <span className={`font-medium ${art === 'rueckwirkend' ? 'text-amber-700' : 'text-blue-700'}`}>
            {art === 'rueckwirkend' ? 'rückwirkend' : 'zukünftig'}
          </span>
          <span className="text-gray-500">Wechsel-Grund:</span>
          <span className="font-medium">{step1.wechsel_grund as string}</span>
        </div>

        <hr className="border-gray-200" />

        <div>
          <p className="font-sans font-semibold text-gray-700 mb-1">KÄUFER</p>
          <div className="grid grid-cols-2 gap-1 text-xs">
            <span className="text-gray-500">Person:</span>
            <span className="font-medium">{(step2.kaeufer_person_name as string) || '–'}</span>
            <span className="text-gray-500">IBAN:</span>
            <span className="font-medium">{(step2.kaeufer_iban as string) || '–'}</span>
          </div>
        </div>

        <div>
          <p className="font-sans font-semibold text-gray-700 mb-1">HAUSGELD-SOLLWERTE KÄUFER</p>
          {Object.entries(hausgeldJeBa).filter(([, v]) => v).map(([ka, betrag]) => (
            <div key={ka} className="grid grid-cols-2 gap-1 text-xs">
              <span className="text-gray-500">{ka}</span>
              <span className="font-medium">{fmtEur(betrag)}</span>
            </div>
          ))}
        </div>

        {art === 'rueckwirkend' && (
          <>
            <hr className="border-gray-200" />
            <div>
              <p className="font-sans font-semibold text-gray-700 mb-1">SOLLSTELLUNGS-KORREKTUREN</p>
              <div className="grid grid-cols-2 gap-1 text-xs">
                <span className="text-gray-500">Stornieren:</span>
                <span className="font-medium">{storniereIds.length} Sollstellung(en)</span>
                <span className="text-gray-500">Erstatten:</span>
                <span className="font-medium">{erstattePositionen.length} Sollstellung(en)</span>
                {erstattePositionen.length > 0 && (
                  <>
                    <span className="text-gray-500">→ Erstattungssumme:</span>
                    <span className="font-medium text-amber-700">{fmtEur(erstattungSumme)}</span>
                    <span className="text-gray-500">→ Verkäufer-IBAN:</span>
                    <span className="font-medium">{(step4.verkaeufer_iban as string) || '–'}</span>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-800">
        Mit Klick auf „Bestätigen &amp; Ausführen" werden alle Änderungen <strong>unwiderruflich</strong> in der Datenbank gespeichert.
        Die Transaktion läuft atomar — bei Fehler wird alles zurückgerollt.
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading} className="bg-green-600 hover:bg-green-700">
          {isLoading ? 'Wird ausgeführt…' : 'Bestätigen & Ausführen'}
        </Button>
      </div>
    </form>
  )
}
