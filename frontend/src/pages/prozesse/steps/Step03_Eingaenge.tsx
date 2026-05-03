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

interface EingangRow {
  id: string
  bezeichnung: string
  strasse: string
  plz: string
  ort: string
  ist_hauptadresse: boolean
}

let nextId = 2

function makeId() {
  return `eingang-${nextId++}`
}

function buildInitialEingaenge(stepsData: Record<string, unknown>, initialData: Record<string, unknown>): EingangRow[] {
  // If we have saved data from this step, use it
  if (Array.isArray(initialData.eingaenge) && initialData.eingaenge.length > 0) {
    return (initialData.eingaenge as EingangRow[]).map((e, i) => ({ ...e, id: e.id ?? makeId(), ist_hauptadresse: i === 0 }))
  }
  // Otherwise pre-populate from step 2 stammdaten
  const s2 = (stepsData['2'] ?? stepsData['step_2'] ?? {}) as Record<string, unknown>
  return [
    {
      id: 'eingang-1',
      bezeichnung: (s2.bezeichnung as string) ?? 'Haupteingang',
      strasse: (s2.strasse as string) ?? '',
      plz: (s2.plz as string) ?? '',
      ort: (s2.ort as string) ?? '',
      ist_hauptadresse: true,
    },
  ]
}

export function Step03_Eingaenge({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const [eingaenge, setEingaenge] = useState<EingangRow[]>(() =>
    buildInitialEingaenge(stepsData, initialData)
  )

  const update = (id: string, field: keyof EingangRow, value: string) => {
    setEingaenge(prev =>
      prev.map(e => (e.id === id ? { ...e, [field]: value } : e))
    )
  }

  const addEingang = () => {
    setEingaenge(prev => [
      ...prev,
      { id: makeId(), bezeichnung: '', strasse: '', plz: '', ort: '', ist_hauptadresse: false },
    ])
  }

  const removeEingang = (id: string) => {
    setEingaenge(prev => prev.filter(e => e.id !== id))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({
      eingaenge: eingaenge.map(({ id: _id, ...rest }, idx) => ({
        ...rest,
        bezeichnung: `Eingang ${idx + 1}`,
      })),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">
        Definieren Sie die Eingänge des Objekts. Der erste Eintrag ist die Hauptadresse und wird aus den Stammdaten vorbelegt.
      </p>

      <div className="space-y-4">
        {eingaenge.map((eingang, idx) => (
          <div
            key={eingang.id}
            className={`rounded-lg border p-4 space-y-3 ${
              eingang.ist_hauptadresse ? 'border-primary-200 bg-primary-50' : 'border-gray-200 bg-white'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-gray-700">
                  Eingang {idx + 1}
                </span>
                {eingang.ist_hauptadresse && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-700">
                    Hauptadresse
                  </span>
                )}
              </div>
              {!eingang.ist_hauptadresse && (
                <button
                  type="button"
                  onClick={() => removeEingang(eingang.id)}
                  className="text-gray-400 hover:text-red-500 transition-colors text-lg leading-none"
                  aria-label="Eingang entfernen"
                >
                  ×
                </button>
              )}
            </div>

            <Input
              label="Straße und Hausnummer *"
              value={eingang.strasse}
              onChange={e => update(eingang.id, 'strasse', e.target.value)}
              placeholder="Musterstraße 1"
              required
            />

            <div className="grid grid-cols-2 gap-3">
              <Input
                label="PLZ *"
                value={eingang.plz}
                onChange={e => update(eingang.id, 'plz', e.target.value)}
                placeholder="12345"
                maxLength={5}
                required
              />
              <Input
                label="Ort *"
                value={eingang.ort}
                onChange={e => update(eingang.id, 'ort', e.target.value)}
                placeholder="Musterstadt"
                required
              />
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addEingang}
        className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 font-medium border border-dashed border-primary-300 rounded-lg px-4 py-2 w-full justify-center hover:bg-primary-50 transition-colors"
      >
        <span className="text-lg leading-none">+</span>
        Weiteren Eingang hinzufügen
      </button>

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
