import React, { useState } from 'react'
import { Button } from '../../../components/ui/Button'
import { Input } from '../../../components/ui/Input'
import { IbanInput } from '../../../components/ui/IbanInput'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

interface KontoRow {
  id: string
  bezeichnung: string
  iban: string
  bic: string
  kontoinhaber: string
  reihenfolge?: number
}

let rkCounter = 1
function makeRkId() { return `rk-${rkCounter++}` }

const DEFAULT_RUECKLAGE_I: KontoRow = {
  id: 'rk-1',
  bezeichnung: 'Instandhaltungsrücklage',
  iban: '', bic: '', kontoinhaber: '',
  reihenfolge: 1,
}

function getInitialBW(initialData: Record<string, unknown>): KontoRow {
  const d = initialData.bewirtschaftungskonto as KontoRow | undefined
  return d ?? { id: 'bw-1', bezeichnung: 'Bewirtschaftungskonto', iban: '', bic: '', kontoinhaber: '' }
}

function getInitialRuecklagen(initialData: Record<string, unknown>): KontoRow[] {
  if (Array.isArray(initialData.ruecklagenkonten) && (initialData.ruecklagenkonten as KontoRow[]).length > 0) {
    return (initialData.ruecklagenkonten as KontoRow[]).map(r => ({ ...r, id: r.id ?? makeRkId() }))
  }
  return [{ ...DEFAULT_RUECKLAGE_I }]
}

function suffixBadge(reihenfolge: number) {
  const n = 910 + reihenfolge
  return `.${n}`
}

export function Step06_Bankkonten({ initialData, onWeiter, isLoading, errors }: StepProps) {
  const [bw, setBW] = useState<KontoRow>(() => getInitialBW(initialData))
  const [ruecklagen, setRuecklagen] = useState<KontoRow[]>(() => getInitialRuecklagen(initialData))
  const [deleteWarning, setDeleteWarning] = useState<string | null>(null)

  const updateBW = (field: keyof KontoRow, value: string) =>
    setBW(prev => ({ ...prev, [field]: value }))

  const updateRK = (id: string, field: keyof KontoRow, value: string) =>
    setRuecklagen(prev => prev.map(r => r.id === id ? { ...r, [field]: value } : r))

  const addRuecklage = () => {
    const nextReihenfolge = ruecklagen.length + 1
    setRuecklagen(prev => [
      ...prev,
      { id: makeRkId(), bezeichnung: '', iban: '', bic: '', kontoinhaber: '', reihenfolge: nextReihenfolge },
    ])
  }

  const removeRuecklage = (id: string) => {
    if (ruecklagen.length === 1) {
      setDeleteWarning(id)
      return
    }
    setDeleteWarning(null)
    setRuecklagen(prev =>
      prev.filter(r => r.id !== id).map((r, i) => ({ ...r, reihenfolge: i + 1 }))
    )
  }

  const confirmDelete = (id: string) => {
    setDeleteWarning(null)
    setRuecklagen(prev =>
      prev.filter(r => r.id !== id).map((r, i) => ({ ...r, reihenfolge: i + 1 }))
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const bwPayload = { konto_typ: 'bewirtschaftung', ...bw, id: undefined }
    const rkPayload = ruecklagen.map(({ id: _id, ...rest }, i) => ({
      konto_typ: 'ruecklage', ...rest, reihenfolge: i + 1,
    }))
    await onWeiter({
      bewirtschaftungskonto: { ...bw, id: undefined },
      ruecklagenkonten: rkPayload,
      bankkonten: [bwPayload, ...rkPayload],
    })
  }

  const bwIbanFehlt = !bw.iban

  return (
    <form onSubmit={handleSubmit} className="space-y-6">

      {/* Bewirtschaftungskonto */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-blue-800">Bewirtschaftungskonto</span>
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">.900</span>
          <span className="text-xs text-blue-600">(genau 1)</span>
          {bwIbanFehlt && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">
              Bankdaten unvollständig — kann jederzeit nachgetragen werden
            </span>
          )}
        </div>

        <Input
          label="Bezeichnung *"
          value={bw.bezeichnung}
          onChange={e => updateBW('bezeichnung', e.target.value)}
          placeholder="Bewirtschaftungskonto"
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <div><label className="block text-xs font-medium text-gray-500 mb-1">IBAN</label>
            <IbanInput value={bw.iban} onChange={v => updateBW('iban', v)} onBicFound={(bic) => { if (!bw.bic) updateBW('bic', bic) }} />
          </div>
          <Input label="BIC" value={bw.bic} onChange={e => updateBW('bic', e.target.value)} placeholder="wird automatisch befüllt" />
        </div>
        <Input label="Kontoinhaber" value={bw.kontoinhaber} onChange={e => updateBW('kontoinhaber', e.target.value)} placeholder="WEG Musterstraße 1" />
      </div>

      {/* Rücklagenkonten */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-700">Rücklagenkonten</span>
        </div>

        {ruecklagen.map((rk, idx) => {
          const n = 910 + (idx + 1)
          const rkIbanFehlt = !rk.iban
          return (
            <div key={rk.id} className="rounded-lg border border-gray-200 p-4 space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-700">Rücklage {idx + 1}</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                    Unterkonto-Suffix: {suffixBadge(idx + 1)}
                  </span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                    Abrechnungsart: {n}
                  </span>
                  {rkIbanFehlt && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">
                      Bankdaten unvollständig
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeRuecklage(rk.id)}
                  className="text-gray-400 hover:text-red-500 transition-colors text-xl leading-none"
                >
                  ×
                </button>
              </div>

              {deleteWarning === rk.id && (
                <div className="rounded bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800">
                  WEG-Objekte benötigen mindestens eine Rücklage. Trotzdem entfernen?{' '}
                  <button type="button" className="font-medium underline" onClick={() => confirmDelete(rk.id)}>
                    Ja, entfernen
                  </button>{' '}·{' '}
                  <button type="button" className="font-medium underline" onClick={() => setDeleteWarning(null)}>
                    Abbrechen
                  </button>
                </div>
              )}

              <Input
                label="Bezeichnung *"
                value={rk.bezeichnung}
                onChange={e => updateRK(rk.id, 'bezeichnung', e.target.value)}
                placeholder="Instandhaltungsrücklage"
                required
              />
              <div className="grid grid-cols-2 gap-3">
                <div><label className="block text-xs font-medium text-gray-500 mb-1">IBAN</label>
                  <IbanInput value={rk.iban} onChange={v => updateRK(rk.id, 'iban', v)} onBicFound={(bic) => { if (!rk.bic) updateRK(rk.id, 'bic', bic) }} />
                </div>
                <Input label="BIC" value={rk.bic} onChange={e => updateRK(rk.id, 'bic', e.target.value)} placeholder="wird automatisch befüllt" />
              </div>
              <Input label="Kontoinhaber" value={rk.kontoinhaber} onChange={e => updateRK(rk.id, 'kontoinhaber', e.target.value)} placeholder="WEG Musterstraße 1" />
            </div>
          )
        })}

        <button
          type="button"
          onClick={addRuecklage}
          className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 font-medium border border-dashed border-primary-300 rounded-lg px-4 py-2 w-full justify-center hover:bg-primary-50 transition-colors"
        >
          <span className="text-lg leading-none">+</span>
          Weitere Rücklage hinzufügen
        </button>
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
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
