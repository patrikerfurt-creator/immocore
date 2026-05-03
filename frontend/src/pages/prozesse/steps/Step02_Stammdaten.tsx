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

interface Stammdaten {
  bezeichnung: string
  strasse: string
  plz: string
  ort: string
  baujahr: string
  verwaltung_seit: string
  wirtschaftsjahr_start: string
}

export function Step02_Stammdaten({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [form, setForm] = useState<Stammdaten>({
    bezeichnung: (initialData.bezeichnung as string) ?? '',
    strasse: (initialData.strasse as string) ?? '',
    plz: (initialData.plz as string) ?? '',
    ort: (initialData.ort as string) ?? '',
    baujahr: (initialData.baujahr as string) ?? '',
    verwaltung_seit: (initialData.verwaltung_seit as string) ?? '',
    wirtschaftsjahr_start: (initialData.wirtschaftsjahr_start as string) ?? '1',
  })

  const set = (key: keyof Stammdaten) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(prev => ({ ...prev, [key]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const daten: Record<string, unknown> = {
      bezeichnung: form.bezeichnung,
      strasse: form.strasse,
      plz: form.plz,
      ort: form.ort,
      verwaltung_seit: form.verwaltung_seit,
      wirtschaftsjahr_start: parseInt(form.wirtschaftsjahr_start, 10),
    }
    if (form.baujahr.trim()) {
      daten.baujahr = parseInt(form.baujahr, 10)
    }
    await onWeiter(daten)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Bezeichnung *"
        value={form.bezeichnung}
        onChange={set('bezeichnung')}
        placeholder="z. B. Musterstraße 1 WEG"
        required
      />

      <Input
        label="Straße und Hausnummer *"
        value={form.strasse}
        onChange={set('strasse')}
        placeholder="z. B. Musterstraße 1"
        required
      />

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="PLZ *"
          value={form.plz}
          onChange={set('plz')}
          placeholder="12345"
          maxLength={5}
          required
        />
        <Input
          label="Ort *"
          value={form.ort}
          onChange={set('ort')}
          placeholder="Musterstadt"
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Baujahr (optional)"
          type="number"
          value={form.baujahr}
          onChange={set('baujahr')}
          placeholder="z. B. 1980"
          min={1800}
          max={new Date().getFullYear()}
        />
        <Input
          label="Verwaltung seit *"
          type="date"
          value={form.verwaltung_seit}
          onChange={set('verwaltung_seit')}
          required
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">
          Wirtschaftsjahr-Beginn (Monat) *
        </label>
        <select
          className="rounded border border-gray-300 px-3 py-2 text-sm outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          value={form.wirtschaftsjahr_start}
          onChange={set('wirtschaftsjahr_start')}
          required
        >
          {[
            [1, 'Januar'], [2, 'Februar'], [3, 'März'], [4, 'April'],
            [5, 'Mai'], [6, 'Juni'], [7, 'Juli'], [8, 'August'],
            [9, 'September'], [10, 'Oktober'], [11, 'November'], [12, 'Dezember'],
          ].map(([val, name]) => (
            <option key={val} value={val}>{name}</option>
          ))}
        </select>
        <p className="text-xs text-gray-400">Standardmäßig Januar (= 1)</p>
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
