import React, { useState } from 'react'
import { Button } from '../../../components/ui/Button'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

type ObjektTyp = 'WEG' | 'ZH' | 'SEV'

const TYPEN: { value: ObjektTyp; label: string; beschreibung: string; disabled: boolean }[] = [
  {
    value: 'WEG',
    label: 'WEG – Wohnungseigentumsgemeinschaft',
    beschreibung: 'Verwaltung von Eigentumswohnungen in einer Gemeinschaft.',
    disabled: false,
  },
  {
    value: 'ZH',
    label: 'ZH – Zinshaus / Mietverwaltung',
    beschreibung: 'Verwaltung von Mietobjekten (Zinshäuser).',
    disabled: false,
  },
  {
    value: 'SEV',
    label: 'SEV – Sondereigentumsverwaltung',
    beschreibung: 'Verwaltung einzelner Eigentumswohnungen im Auftrag.',
    disabled: false,
  },
]

export function Step01_Objekttyp({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [selected, setSelected] = useState<ObjektTyp>(
    (initialData.objekt_typ as ObjektTyp) ?? 'WEG'
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({ objekt_typ: selected })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <p className="text-sm text-gray-600 mb-4">
          Wählen Sie den Verwaltungstyp für das neue Objekt.
        </p>
        <div className="space-y-3">
          {TYPEN.map(typ => (
            <label
              key={typ.value}
              className={`flex items-start gap-3 p-4 rounded-lg border-2 transition-all ${
                typ.disabled
                  ? 'border-gray-100 bg-gray-50 cursor-not-allowed opacity-50'
                  : selected === typ.value
                  ? 'border-primary-500 bg-primary-50 cursor-pointer'
                  : 'border-gray-200 bg-white cursor-pointer hover:border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="objekt_typ"
                value={typ.value}
                checked={selected === typ.value}
                onChange={() => setSelected(typ.value)}
                disabled={typ.disabled}
                className="mt-0.5 accent-primary-600"
              />
              <div>
                <span className={`text-sm font-semibold ${typ.disabled ? 'text-gray-400' : 'text-gray-800'}`}>
                  {typ.label}
                </span>
                <p className={`text-xs mt-0.5 ${typ.disabled ? 'text-gray-400 italic' : 'text-gray-500'}`}>
                  {typ.beschreibung}
                </p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
