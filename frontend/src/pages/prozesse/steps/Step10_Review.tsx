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

interface AccordionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function Accordion({ title, children, defaultOpen = false }: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center justify-between w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="text-sm font-semibold text-gray-700">{title}</span>
        <svg
          className={`w-4 h-4 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-4 py-3 bg-white">
          {children}
        </div>
      )}
    </div>
  )
}

function StepSummary({ data }: { data: unknown }) {
  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) {
    return <p className="text-sm text-gray-400 italic">Keine Daten vorhanden.</p>
  }
  return (
    <pre className="text-xs bg-gray-50 rounded p-3 overflow-auto max-h-48 text-gray-700 border border-gray-100">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function Stammdaten({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {([
        ['Bezeichnung', data.bezeichnung],
        ['Straße', data.strasse],
        ['PLZ', data.plz],
        ['Ort', data.ort],
        ['Baujahr', data.baujahr ?? '—'],
        ['Verwaltung seit', data.verwaltung_seit],
        ['WJ-Start (Monat)', data.wirtschaftsjahr_start],
      ] as [string, unknown][]).map(([label, value]) => (
        <div key={label}>
          <dt className="text-gray-500 text-xs">{label}</dt>
          <dd className="font-medium text-gray-800">{String(value ?? '—')}</dd>
        </div>
      ))}
    </dl>
  )
}

function EinheitenList({ data }: { data: Record<string, unknown> }) {
  const einheiten = data.einheiten as Record<string, string>[] | undefined
  if (!Array.isArray(einheiten) || einheiten.length === 0) {
    return <p className="text-sm text-gray-400">Keine Einheiten.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="text-left pb-1 text-gray-500 font-medium">Nr.</th>
            <th className="text-left pb-1 text-gray-500 font-medium">Typ</th>
            <th className="text-left pb-1 text-gray-500 font-medium">Lage</th>
            <th className="text-right pb-1 text-gray-500 font-medium">Fläche</th>
            <th className="text-right pb-1 text-gray-500 font-medium">MEA</th>
          </tr>
        </thead>
        <tbody>
          {einheiten.map((e, i) => (
            <tr key={i} className="border-b border-gray-50">
              <td className="py-1 pr-2 font-medium text-gray-700">{e.einheit_nr}</td>
              <td className="py-1 pr-2 text-gray-600">{e.einheit_typ}</td>
              <td className="py-1 pr-2 text-gray-600">{e.lage || '—'}</td>
              <td className="py-1 pr-2 text-right text-gray-600">{e.flaeche_qm ? `${e.flaeche_qm} m²` : '—'}</td>
              <td className="py-1 text-right text-gray-600">{e.miteigentumsanteil ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BankkontenSummary({ data }: { data: Record<string, unknown> }) {
  const bw = data.bewirtschaftungskonto as Record<string, string> | undefined
  const rk = data.ruecklagenkonten as Record<string, string>[] | undefined
  return (
    <div className="space-y-2 text-sm">
      {bw && (
        <div>
          <span className="text-xs font-semibold text-gray-500 uppercase">Bewirtschaftungskonto .900</span>
          <p className="text-gray-700 font-mono text-xs mt-0.5">{bw.iban}</p>
          <p className="text-gray-500 text-xs">{bw.kontoinhaber}</p>
        </div>
      )}
      {Array.isArray(rk) && rk.map((r, i) => (
        <div key={i}>
          <span className="text-xs font-semibold text-gray-500 uppercase">Rücklage .9{11 + i}</span>
          <p className="text-gray-700 font-mono text-xs mt-0.5">{r.iban}</p>
          <p className="text-gray-500 text-xs">{r.kontoinhaber} — {r.bezeichnung}</p>
        </div>
      ))}
    </div>
  )
}

export function Step10_Review({ stepsData, onWeiter, isLoading, errors }: StepProps) {
  const s2 = (stepsData['2'] ?? stepsData['step_2'] ?? {}) as Record<string, unknown>
  const s4 = (stepsData['4'] ?? stepsData['step_4'] ?? {}) as Record<string, unknown>
  const s6 = (stepsData['6'] ?? stepsData['step_6'] ?? {}) as Record<string, unknown>

  const handleAbschliessen = async () => {
    await onWeiter({ reviewed: true })
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Überprüfen Sie alle Eingaben. Nach dem Aktivieren wird das Objekt angelegt und alle Daten gespeichert.
      </p>

      <div className="space-y-2">
        <Accordion title="1 – Objekttyp" defaultOpen={false}>
          <StepSummary data={stepsData['1'] ?? stepsData['step_1']} />
        </Accordion>

        <Accordion title="2 – Stammdaten" defaultOpen>
          {Object.keys(s2).length > 0 ? <Stammdaten data={s2} /> : <StepSummary data={null} />}
        </Accordion>

        <Accordion title="3 – Eingänge" defaultOpen={false}>
          <StepSummary data={stepsData['3'] ?? stepsData['step_3']} />
        </Accordion>

        <Accordion title="4 – Einheiten" defaultOpen={false}>
          <EinheitenList data={s4} />
        </Accordion>

        <Accordion title="5 – Eigentümer" defaultOpen={false}>
          <StepSummary data={stepsData['5'] ?? stepsData['step_5']} />
        </Accordion>

        <Accordion title="6 – Bankkonten" defaultOpen={false}>
          {Object.keys(s6).length > 0 ? <BankkontenSummary data={s6} /> : <StepSummary data={null} />}
        </Accordion>

        <Accordion title="7 – Kontenrahmen" defaultOpen={false}>
          <StepSummary data={stepsData['7'] ?? stepsData['step_7']} />
        </Accordion>

        <Accordion title="8 – Verträge" defaultOpen={false}>
          <StepSummary data={stepsData['8'] ?? stepsData['step_8']} />
        </Accordion>

        <Accordion title="9 – Freigabelimits" defaultOpen={false}>
          <StepSummary data={stepsData['9'] ?? stepsData['step_9']} />
        </Accordion>
      </div>

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button
          type="button"
          onClick={handleAbschliessen}
          disabled={isLoading}
          className="bg-green-600 hover:bg-green-700 focus:ring-green-500"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Aktiviere…
            </span>
          ) : (
            'Jetzt aktivieren'
          )}
        </Button>
      </div>
    </div>
  )
}
