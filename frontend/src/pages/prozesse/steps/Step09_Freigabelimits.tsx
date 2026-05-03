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

type Rolle = 'auto' | 'objektmanager' | 'sachbearbeiter' | 'geschaeftsfuehrer'

interface FreigabeRow {
  id: string
  bis: string
  rolle: Rolle
  frist_tage: string
  beschreibung: string
}

const ROLLEN: { value: Rolle; label: string }[] = [
  { value: 'auto',             label: 'Automatisch (keine Freigabe)' },
  { value: 'objektmanager',   label: 'Objektmanager' },
  { value: 'sachbearbeiter',  label: 'Sachbearbeiter' },
  { value: 'geschaeftsfuehrer', label: 'Geschäftsführer' },
]

const DEFAULT_LIMITS: FreigabeRow[] = [
  { id: 'fl-1', bis: '500',  rolle: 'auto',             frist_tage: '0', beschreibung: 'Automatische Freigabe' },
  { id: 'fl-2', bis: '5000', rolle: 'objektmanager',    frist_tage: '3', beschreibung: 'Objektmanager-Freigabe' },
  { id: 'fl-3', bis: '',     rolle: 'geschaeftsfuehrer', frist_tage: '5', beschreibung: 'Geschäftsführer-Freigabe' },
]

export function rowsFromGrenzen(grenzen: unknown): FreigabeRow[] {
  if (Array.isArray(grenzen) && grenzen.length > 0) {
    return (grenzen as Record<string, unknown>[]).map((l, i) => ({
      id: (l.id as string) ?? `fl-${i + 1}`,
      bis: String(l.bis ?? ''),
      rolle: (l.rolle as Rolle) ?? 'auto',
      frist_tage: String(l.frist_tage ?? '0'),
      beschreibung: String(l.beschreibung ?? l.eskalation ?? ''),
    }))
  }
  return DEFAULT_LIMITS
}

function getInitialLimits(initialData: Record<string, unknown>): FreigabeRow[] {
  return rowsFromGrenzen(initialData.grenzen ?? initialData.freigabelimits)
}

export function Step09_Freigabelimits({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [limits, setLimits] = useState<FreigabeRow[]>(() => getInitialLimits(initialData))

  const update = (id: string, field: keyof FreigabeRow, value: string) => {
    setLimits(prev => prev.map(l => l.id === id ? { ...l, [field]: value } : l))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({
      grenzen: limits.map(({ id: _id, ...rest }) => ({
        ...rest,
        bis: rest.bis ? parseFloat(rest.bis) : null,
        frist_tage: parseInt(rest.frist_tage, 10),
      })),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">
        Definieren Sie die Freigabelimits für Zahlungen. Jede Stufe legt fest, wer bis zu welchem Betrag freigeben darf.
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm min-w-[600px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Stufe</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Bis (€)</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Rolle</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Frist (Tage)</th>
              <th className="text-left px-3 py-2 font-medium text-gray-600">Beschreibung</th>
            </tr>
          </thead>
          <tbody>
            {limits.map((limit, idx) => (
              <tr key={limit.id} className="border-t border-gray-100 hover:bg-gray-50">
                <td className="px-3 py-2 text-gray-500 font-medium">{idx + 1}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={limit.bis}
                      onChange={e => update(limit.id, 'bis', e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[100px]"
                      placeholder={idx === limits.length - 1 ? '∞' : '0'}
                      min={0}
                      step="1"
                    />
                    {idx === limits.length - 1 && (
                      <span className="text-xs text-gray-400">(leer = unbegrenzt)</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <select
                    value={limit.rolle}
                    onChange={e => update(limit.id, 'rolle', e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                  >
                    {ROLLEN.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2">
                  <input
                    type="number"
                    value={limit.frist_tage}
                    onChange={e => update(limit.id, 'frist_tage', e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[70px]"
                    min={0}
                    step={1}
                  />
                </td>
                <td className="px-3 py-2">
                  <input
                    type="text"
                    value={limit.beschreibung}
                    onChange={e => update(limit.id, 'beschreibung', e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-full"
                    placeholder="Beschreibung der Eskalationsstufe"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-md bg-blue-50 border border-blue-100 p-3">
        <p className="text-xs text-blue-700">
          <strong>Hinweis:</strong> Bei der letzten Stufe (ohne Betragslimit) gilt diese Regelung für alle Beträge oberhalb der vorigen Stufe.
          Stufe mit Frist 0 Tage = Sofortfreigabe.
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
        <Button type="submit" disabled={isLoading}>
          {isLoading ? 'Speichern…' : 'Weiter – Überprüfung'}
        </Button>
      </div>
    </form>
  )
}
