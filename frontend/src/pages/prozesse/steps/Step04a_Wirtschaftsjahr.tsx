import React, { useState } from 'react'
import { Button } from '../../../components/ui/Button'
import { Input } from '../../../components/ui/Input'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

const MONAT_NAMEN = [
  '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

function wjDaten(jahr: number, beginnMonat: number): { von: string; bis: string } {
  const vonDate = new Date(jahr, beginnMonat - 1, 1)
  const bisDate = new Date(
    beginnMonat === 1 ? jahr : jahr + 1,
    beginnMonat === 1 ? 11 : beginnMonat - 2,
    0,
  )
  const fmt = (d: Date) =>
    d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
  return { von: fmt(vonDate), bis: fmt(bisDate) }
}

export function Step04a_Wirtschaftsjahr({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const aktuellesJahr = new Date().getFullYear()

  // beginn_monat comes from step 2 (Stammdaten)
  const step2 = (stepsData['2'] ?? stepsData['step_2'] ?? {}) as Record<string, unknown>
  const beginnMonat = parseInt(String(step2.wirtschaftsjahr_start ?? '1'), 10) || 1

  const [jahr, setJahr] = useState<string>(
    String((initialData.jahr as number | undefined) ?? aktuellesJahr)
  )

  const jahrNum = parseInt(jahr, 10)
  const jahrGueltig = !isNaN(jahrNum) && jahrNum >= 2000 && jahrNum <= aktuellesJahr + 1
  const zeitraum = jahrGueltig ? wjDaten(jahrNum, beginnMonat) : null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({ jahr: jahrNum })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <p className="text-sm text-gray-600">
        Das erste Wirtschaftsjahr legt den Buchungsrahmen für dieses Objekt fest.
        Für Folgejahre können Sie später über die Objekt-Übersicht neue Wirtschaftsjahre eröffnen.
      </p>

      <div className="flex flex-col gap-1">
        <Input
          label={`Wirtschaftsjahr * (${aktuellesJahr - 1} – ${aktuellesJahr + 1})`}
          type="number"
          value={jahr}
          onChange={e => setJahr(e.target.value)}
          min={2000}
          max={aktuellesJahr + 1}
          required
        />
      </div>

      <div className="rounded-md bg-gray-50 border border-gray-200 p-4 space-y-2 text-sm">
        <div className="flex gap-2">
          <span className="font-medium text-gray-600 w-36">Beginn-Monat:</span>
          <span className="text-gray-800">{MONAT_NAMEN[beginnMonat]} ({beginnMonat})</span>
        </div>
        {zeitraum ? (
          <>
            <div className="flex gap-2">
              <span className="font-medium text-gray-600 w-36">Zeitraum von:</span>
              <span className="text-gray-800">{zeitraum.von}</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-gray-600 w-36">Zeitraum bis:</span>
              <span className="text-gray-800">{zeitraum.bis}</span>
            </div>
          </>
        ) : (
          <p className="text-gray-400 italic">Bitte gültiges Jahr eingeben.</p>
        )}
        <p className="text-xs text-gray-400 pt-1">
          Der Beginn-Monat wird aus Schritt 2 (Stammdaten) übernommen.
          Um ihn zu ändern, gehen Sie zurück zu Schritt 2.
        </p>
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || !jahrGueltig}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
