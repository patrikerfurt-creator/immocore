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

interface VertragRow {
  wohnungsbezeichnung: string
  person_name: string
  beginn: string
  hausgeld: Record<string, string>
}

function getEinheiten(stepsData: Record<string, unknown>): { wohnungsbezeichnung: string }[] {
  const s4 = (stepsData['4'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s4.einheiten)) {
    return (s4.einheiten as Record<string, string>[]).map(e => ({ wohnungsbezeichnung: e.wohnungsbezeichnung ?? '' }))
  }
  return []
}

function getPersonName(stepsData: Record<string, unknown>, wbez: string): string {
  const s5 = (stepsData['5'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s5.zuordnungen)) {
    const z = (s5.zuordnungen as { wohnungsbezeichnung: string; person_name: string }[])
      .find(x => x.wohnungsbezeichnung === wbez)
    return z?.person_name ?? '—'
  }
  return '—'
}

function getRuecklagenkonten(stepsData: Record<string, unknown>): { suffix: string; bezeichnung: string }[] {
  const s6 = (stepsData['6'] ?? {}) as Record<string, unknown>
  if (Array.isArray(s6.ruecklagenkonten)) {
    return (s6.ruecklagenkonten as { bezeichnung: string }[]).map((r, i) => ({
      suffix: `.9${11 + i}`,
      bezeichnung: r.bezeichnung || `Rücklage ${i + 1}`,
    }))
  }
  return [{ suffix: '.911', bezeichnung: 'Instandhaltungsrücklage' }]
}

function buildInitialRows(
  einheiten: { wohnungsbezeichnung: string }[],
  stepsData: Record<string, unknown>,
  ruecklagen: { suffix: string }[],
  initialData: Record<string, unknown>
): VertragRow[] {
  if (Array.isArray(initialData.vertraege) && initialData.vertraege.length > 0) {
    return (initialData.vertraege as VertragRow[]).map(r => ({
      ...r,
      person_name: getPersonName(stepsData, r.wohnungsbezeichnung),
    }))
  }
  return einheiten.map(e => {
    const hausgeld: Record<string, string> = { '.900': '' }
    ruecklagen.forEach(r => { hausgeld[r.suffix] = '' })
    hausgeld['.940'] = '0'
    return {
      wohnungsbezeichnung: e.wohnungsbezeichnung,
      person_name: getPersonName(stepsData, e.wohnungsbezeichnung),
      beginn: '',
      hausgeld,
    }
  })
}

export function Step08_Vertraege({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const einheiten = getEinheiten(stepsData)
  const ruecklagen = getRuecklagenkonten(stepsData)

  const [rows, setRows] = useState<VertragRow[]>(() =>
    buildInitialRows(einheiten, stepsData, ruecklagen, initialData)
  )

  const updateRow = (wbez: string, field: 'beginn', value: string) => {
    setRows(prev => prev.map(r => r.wohnungsbezeichnung === wbez ? { ...r, [field]: value } : r))
  }

  const updateHausgeld = (wbez: string, kontoart: string, value: string) => {
    setRows(prev => prev.map(r =>
      r.wohnungsbezeichnung === wbez
        ? { ...r, hausgeld: { ...r.hausgeld, [kontoart]: value } }
        : r
    ))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({ vertraege: rows.map(({ person_name: _pn, ...rest }) => rest) })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">
        Legen Sie Vertragsbeginn und monatliche Sollbeträge für jede Einheit fest.
      </p>

      {rows.length === 0 && (
        <div className="rounded-md bg-amber-50 p-3">
          <p className="text-sm text-amber-700">Keine Einheiten gefunden. Bitte Schritt 4 zuerst ausfüllen.</p>
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm" style={{ minWidth: `${480 + ruecklagen.length * 120}px` }}>
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Einheit</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Eigentümer</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Beginn *</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">.900 (€/Mo) *</th>
                {ruecklagen.map(rk => (
                  <th key={rk.suffix} className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">
                    {rk.suffix}
                    <span className="block text-xs font-normal text-gray-400">{rk.bezeichnung}</span>
                  </th>
                ))}
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">.940 (€/Mo)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.wohnungsbezeichnung} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-700 whitespace-nowrap">{row.wohnungsbezeichnung}</td>
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap max-w-[160px] truncate">
                    {row.person_name}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="date"
                      value={row.beginn}
                      onChange={e => updateRow(row.wohnungsbezeichnung, 'beginn', e.target.value)}
                      required
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[130px]"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      value={row.hausgeld['.900'] ?? ''}
                      onChange={e => updateHausgeld(row.wohnungsbezeichnung, '.900', e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[90px]"
                      placeholder="0.00"
                      min={0}
                      step="0.01"
                    />
                  </td>
                  {ruecklagen.map(rk => (
                    <td key={rk.suffix} className="px-3 py-2">
                      <input
                        type="number"
                        value={row.hausgeld[rk.suffix] ?? ''}
                        onChange={e => updateHausgeld(row.wohnungsbezeichnung, rk.suffix, e.target.value)}
                        className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[90px]"
                        placeholder="0.00"
                        min={0}
                        step="0.01"
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      value={row.hausgeld['.940'] ?? ''}
                      onChange={e => updateHausgeld(row.wohnungsbezeichnung, '.940', e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none w-[90px]"
                      placeholder="0"
                      min={0}
                      step="0.01"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
