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

interface KontoRow {
  kontonummer: string
  kontoname: string
  abrechnungsart: string
  direktes_buchen: boolean
  verteilerschluessel: string
  kontoart: 'standard' | 'summierung' | 'unterkonto'
  arge_konto: boolean
  aktiv: boolean
  generiert?: boolean
}

const VS_OPTIONS = [
  { value: '', label: '–' },
  { value: '010', label: '010 – MEA' },
  { value: '030', label: '030 – Kopf ges.' },
  { value: '031', label: '031 – Kopf Whg.' },
  { value: '032', label: '032 – Kopf Stpl.' },
  { value: '100', label: '100 – Direkt' },
  { value: '101', label: '101 – Direkt Eig.' },
  { value: '140', label: '140 – Verbr.' },
]

// 70 Muster-Sachkonten (WEG) aus CSV-Fixture
const MUSTER_KONTEN: KontoRow[] = [
  { kontonummer: '09911', kontoname: 'Rücklagenbestandskonto',                  abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '13600', kontoname: 'DCL-Kreditor',                            abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '13650', kontoname: 'DCL-Debitor',                             abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '13700', kontoname: 'Ungeklärte Posten',                       abrechnungsart: '',    direktes_buchen: true,  verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '14600', kontoname: 'Bankübertrag / Geldtransit',              abrechnungsart: '',    direktes_buchen: true,  verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '16000', kontoname: 'Kasse',                                   abrechnungsart: '',    direktes_buchen: true,  verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '18000', kontoname: 'Bank 1',                                  abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '18911', kontoname: 'Bank 2 Rücklage 1',                       abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '19000', kontoname: 'Aktive Rechnungsabgrenzung (Folgejahr)',  abrechnungsart: '',    direktes_buchen: true,  verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '39000', kontoname: 'Passive Rechnungsabgrenzung (Vorjahr)',   abrechnungsart: '',    direktes_buchen: true,  verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41900', kontoname: 'Erlöse Hausgeld VZ',                      abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41911', kontoname: 'Erlöse Rücklage I',                       abrechnungsart: '911', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41930', kontoname: 'Erlöse Sonderumlage',                     abrechnungsart: '930', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41940', kontoname: 'Erlöse Mahngebühren',                     abrechnungsart: '940', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41941', kontoname: 'Erlöse Rücklastschriftgebühren',          abrechnungsart: '941', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '41950', kontoname: 'Erlöse Abrechnung VJ',                    abrechnungsart: '950', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '49500', kontoname: 'Erlöse aus Hausgeldklagen',               abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '49600', kontoname: 'Sonstige Erlöse',                         abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '49700', kontoname: 'Erlöse Versicherungsentschädigungen',     abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '49911', kontoname: 'Erlöse Entnahme IHR I',                   abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50100', kontoname: 'Hausmeister',                             abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50110', kontoname: 'Hausreinigung',                           abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50120', kontoname: 'Winterdienst',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50130', kontoname: 'Außenanlagen',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50200', kontoname: 'Straßenreinigung',                        abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50210', kontoname: 'Niederschlagwasser',                      abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50230', kontoname: 'Müllabfuhr',                              abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50240', kontoname: 'Allgemeinstrom',                          abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50299', kontoname: 'Heiz- und Wasserkosten nach Verbrauch',   abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'summierung', arge_konto: false, aktiv: true },
  { kontonummer: '50300', kontoname: 'Wasser',                                  abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50310', kontoname: 'Abwasser',                                abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50320', kontoname: 'Gas/Öl/Wärme',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50330', kontoname: 'Messdienst/Gerätemiete',                  abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50340', kontoname: 'Heizungswartung',                         abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50350', kontoname: 'Schornsteinfeger',                        abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50360', kontoname: 'Heizungsstrom (aus Allgemeinstrom)',       abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '',    kontoart: 'unterkonto', arge_konto: true,  aktiv: true },
  { kontonummer: '50390', kontoname: 'Feuerstättenbescheid',                    abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50400', kontoname: 'Betriebskosten Aufzug',                   abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50500', kontoname: 'Wartung',                                 abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50510', kontoname: 'Wartung Brandschutz',                     abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50520', kontoname: 'Wartung Wasser/Abwasseranlage',           abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50530', kontoname: 'Wartung Rolltor TG',                      abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50540', kontoname: 'Wartung Dach/Rinnenreinigung',            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50550', kontoname: 'Wartung Parker',                          abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50560', kontoname: 'Wartung Rauchwarnmelder',                 abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50590', kontoname: 'Schädlingsbekämpfung',                    abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50600', kontoname: 'Kabelempfang',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50700', kontoname: 'Versicherungen',                          abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '50800', kontoname: 'Legionellenprüfung',                      abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55100', kontoname: 'Verwaltergebühr Wohnung',                 abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '031', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55110', kontoname: 'Verwaltergebühr Stellplätze',             abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '032', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55111', kontoname: 'Nichtteilnahme am Lastschriftverfahren',  abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '100', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55112', kontoname: 'Aufwand HNDL',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '030', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55113', kontoname: 'Abrechenbare Auslagen der Verwaltung',    abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55115', kontoname: 'Raummiete',                               abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55200', kontoname: 'Reparaturen',                             abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55210', kontoname: 'Instandsetzung Außenanlagen',             abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55290', kontoname: 'Reparatur VS',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55300', kontoname: 'Reparaturen Aufzug',                      abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55350', kontoname: 'Sanierung',                               abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55400', kontoname: 'Rechtskosten',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55410', kontoname: 'Beratungskosten',                         abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55500', kontoname: 'Bankgebühren',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55900', kontoname: 'Direktkosten Eigentümer',                 abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '101', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '55905', kontoname: 'Mahngebühren',                            abrechnungsart: '900', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '57911', kontoname: 'Rücklage I',                              abrechnungsart: '911', direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '90000', kontoname: 'Saldenvorträge Sachkonten',               abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '90080', kontoname: 'Saldenvorträge Debitoren',                abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '90090', kontoname: 'Saldenvorträge Kreditoren',               abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
  { kontonummer: '91000', kontoname: 'JA Buchung Vortrag Sachkonten',           abrechnungsart: '',    direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard',   arge_konto: false, aktiv: true },
]

function generateRuecklagenKonten(stepsData: Record<string, unknown>): KontoRow[] {
  const step5 = (stepsData['5'] ?? {}) as Record<string, unknown>
  const rks = Array.isArray(step5.ruecklagenkonten)
    ? (step5.ruecklagenkonten as Array<{ reihenfolge: number }>)
    : []

  return rks
    .filter(rk => Number(rk.reihenfolge) >= 2)
    .flatMap(rk => {
      const r = Number(rk.reihenfolge)
      const n = 910 + r
      const abr = String(n)
      return [
        { kontonummer: `0991${r}`, kontoname: `Bank ${n} Rücklage ${r}`,     abrechnungsart: abr, direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard' as const, arge_konto: false, aktiv: true, generiert: true },
        { kontonummer: `5791${r}`, kontoname: `Rücklage ${r}`,               abrechnungsart: abr, direktes_buchen: false, verteilerschluessel: '010', kontoart: 'standard' as const, arge_konto: false, aktiv: true, generiert: true },
        { kontonummer: `4191${r}`, kontoname: `Erlöse Rücklage ${r}`,        abrechnungsart: abr, direktes_buchen: false, verteilerschluessel: '',    kontoart: 'standard' as const, arge_konto: false, aktiv: true, generiert: true },
      ]
    })
}

function getInitialKonten(initialData: Record<string, unknown>, stepsData: Record<string, unknown>): KontoRow[] {
  const generated = generateRuecklagenKonten(stepsData)
  const base = [...MUSTER_KONTEN, ...generated]

  const saved = Array.isArray(initialData.konten) ? (initialData.konten as Partial<KontoRow>[]) : []
  if (saved.length === 0) return base

  const savedMap = new Map(saved.map(k => [k.kontonummer, k]))
  return base.map(k => {
    const s = savedMap.get(k.kontonummer)
    if (!s) return k
    return {
      ...k,
      aktiv: s.aktiv ?? k.aktiv,
      direktes_buchen: s.direktes_buchen ?? k.direktes_buchen,
      verteilerschluessel: s.verteilerschluessel ?? k.verteilerschluessel,
    }
  })
}

export function Step07_Kontenrahmen({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const [konten, setKonten] = useState<KontoRow[]>(() => getInitialKonten(initialData, stepsData))

  const updateKonto = (kontonummer: string, field: keyof KontoRow, value: unknown) =>
    setKonten(prev => prev.map(k => k.kontonummer === kontonummer ? { ...k, [field]: value } : k))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onWeiter({ konten })
  }

  const genCount = konten.filter(k => k.generiert).length

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-center gap-3 text-sm text-gray-600 flex-wrap">
        <span><strong className="text-gray-900">{MUSTER_KONTEN.length}</strong> Muster-Konten</span>
        {genCount > 0 && (
          <span>+ <strong className="text-gray-900">{genCount}</strong> generierte Rücklagen-Konten</span>
        )}
        <span className="text-gray-300">|</span>
        <span>Aktiv: <strong className="text-gray-700">{konten.filter(k => k.aktiv).length}</strong> von {konten.length}</span>
      </div>

      <div className="rounded-lg border border-gray-200 overflow-x-auto">
        <div className="overflow-y-auto max-h-[520px]">
          <table className="w-full text-sm min-w-[680px]">
            <thead className="bg-gray-50 border-b border-gray-200 sticky top-0 z-10">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Nr.</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600">Kontoname</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Abr.</th>
                <th className="text-left px-3 py-2 font-medium text-gray-600 whitespace-nowrap">VS</th>
                <th className="text-center px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Dir.</th>
                <th className="text-center px-3 py-2 font-medium text-gray-600 whitespace-nowrap">Aktiv</th>
              </tr>
            </thead>
            <tbody>
              {konten.map(konto => (
                <tr
                  key={konto.kontonummer}
                  className={`border-t border-gray-100 transition-colors ${!konto.aktiv ? 'opacity-40 bg-gray-50/40' : 'hover:bg-gray-50'}`}
                >
                  <td className="px-3 py-1.5 font-mono text-xs text-gray-600 whitespace-nowrap">{konto.kontonummer}</td>
                  <td className="px-3 py-1.5 text-gray-800">
                    {konto.kontoname}
                    {konto.generiert && (
                      <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">Generiert</span>
                    )}
                    {konto.kontoart === 'summierung' && (
                      <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500">Σ</span>
                    )}
                    {konto.kontoart === 'unterkonto' && (
                      <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-500">↪</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-gray-500 whitespace-nowrap">{konto.abrechnungsart || '–'}</td>
                  <td className="px-3 py-1.5">
                    <select
                      value={konto.verteilerschluessel}
                      onChange={e => updateKonto(konto.kontonummer, 'verteilerschluessel', e.target.value)}
                      disabled={!konto.aktiv}
                      className="rounded border border-gray-300 px-1.5 py-0.5 text-xs focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none disabled:opacity-50"
                    >
                      {VS_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={konto.direktes_buchen}
                      onChange={() => updateKonto(konto.kontonummer, 'direktes_buchen', !konto.direktes_buchen)}
                      disabled={!konto.aktiv}
                      className="accent-primary-600 w-4 h-4 disabled:opacity-50"
                    />
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={konto.aktiv}
                      onChange={() => updateKonto(konto.kontonummer, 'aktiv', !konto.aktiv)}
                      className="accent-primary-600 w-4 h-4"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
