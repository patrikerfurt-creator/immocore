import React, { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../../components/ui/Button'
import { personenApi } from '../../../api/personen'
import { buchhaltungApi } from '../../../api/buchhaltung'
import type { Abrechnungsart, EigentumsVerhaeltnis, HausgeldHistorie } from '../../../types'

interface StepProps {
  prozessId: string
  stepsData: Record<string, unknown>
  initialData: Record<string, unknown>
  onWeiter: (daten: Record<string, unknown>) => Promise<void>
  isLoading: boolean
  errors: string[]
}

// Fallback, falls die Abrechnungsarten des Objekts (noch) nicht geladen sind.
// Sie sind absichtlich NICHT die feste Zeilenliste: hier stand vorher nur
// .900/.911/.912/.940, wodurch jede weitere Abrechnungsart des Objekts
// (z.B. 915, 919) stillschweigend aus dem Käufer-Soll fiel — der Käufer wurde
// dann dauerhaft zu niedrig belastet.
const BA_FALLBACK = [
  { kontoart: '.900', bezeichnung: 'Hausgeld lfd.' },
  { kontoart: '.911', bezeichnung: '1. Rücklage' },
  { kontoart: '.912', bezeichnung: '2. Rücklage' },
  { kontoart: '.940', bezeichnung: 'Sonderumlage' },
]


function fmtDate(iso: string): string {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

// Find the applicable HausgeldHistorie entry for a BA at a given date.
// "Applicable" = latest entry with gueltig_ab <= refDate (or null gueltig_bis means open)
function getEntryAt(entries: HausgeldHistorie[], kontoart: string, refDate: string): HausgeldHistorie | undefined {
  const code = kontoart.replace(/^\./, '')
  const matching = entries
    .filter(h => h.abrechnungsart_code === code && h.gueltig_ab <= refDate)
    .sort((a, b) => b.gueltig_ab.localeCompare(a.gueltig_ab))
  return matching[0]
}

// Find all future entries (gueltig_ab > today) for a BA
function getFutureEntries(entries: HausgeldHistorie[], kontoart: string, today: string): HausgeldHistorie[] {
  const code = kontoart.replace(/^\./, '')
  return entries
    .filter(h => h.abrechnungsart_code === code && h.gueltig_ab > today)
    .sort((a, b) => a.gueltig_ab.localeCompare(b.gueltig_ab))
}

export function EW_Step03_HausgeldSollwerte({ stepsData, initialData, onWeiter, isLoading, errors }: StepProps) {
  const step1 = (stepsData['1'] ?? {}) as Record<string, unknown>
  const objektId      = (stepsData as { objekt_id?: string }).objekt_id
  const einheitId     = step1.einheit_id as string | undefined
  const wirkungsDatum = (step1.wirkungs_periode as string | undefined) ?? ''
  const today         = new Date().toISOString().slice(0, 10)

  const { data: evListe } = useQuery({
    queryKey: ['ev-einheit', einheitId],
    queryFn:  () => personenApi.eigentumsverhaeltnisse({ einheit: einheitId! }),
    enabled:  !!einheitId,
  })
  const aktivesEv = evListe?.find((ev: EigentumsVerhaeltnis) => ev.ist_aktiv)
  const eintraege: HausgeldHistorie[] = aktivesEv?.hausgeld_eintraege ?? []

  const { data: abrechnungsarten } = useQuery({
    queryKey: ['abrechnungsarten', objektId],
    queryFn:  () => buchhaltungApi.abrechnungsarten(objektId!),
    enabled:  !!objektId,
  })

  // Zeilen aus den Abrechnungsarten des Objekts, ergänzt um alles, was in der
  // Verkäufer-Historie vorkommt — damit keine Position unterschlagen wird.
  const BA_ZEILEN = useMemo(() => {
    const map = new Map<string, { kontoart: string; bezeichnung: string }>()
    for (const a of (abrechnungsarten ?? []) as Abrechnungsart[]) {
      if (a.aktiv) map.set(a.code, { kontoart: `.${a.code}`, bezeichnung: a.bezeichnung })
    }
    for (const h of eintraege) {
      const code = h.abrechnungsart_code
      if (code && !map.has(code)) {
        map.set(code, { kontoart: `.${code}`, bezeichnung: h.abrechnungsart_bezeichnung || code })
      }
    }
    if (map.size === 0) return BA_FALLBACK
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, v]) => v)
  }, [abrechnungsarten, eintraege])

  // Saved data from a previous visit to this step (edit mode)
  const savedHje = (initialData.hausgeld_je_ba ?? {}) as Record<string, string>
  const [hausgeldJeBa, setHausgeldJeBa] = useState<Record<string, string>>(savedHje)

  // Pre-fill from Verkäufer-Historie when EV loads (only if nothing saved yet)
  useEffect(() => {
    if (!aktivesEv || eintraege.length === 0) return
    if (Object.keys(hausgeldJeBa).some(k => hausgeldJeBa[k] !== '')) return

    const refDate = wirkungsDatum || today
    const prefill: Record<string, string> = {}
    for (const row of BA_ZEILEN) {
      // Use the rate applicable at wirkungs_periode (picks up future Wirtschaftsplan automatically)
      const entry = getEntryAt(eintraege, row.kontoart, refDate)
      if (entry) prefill[row.kontoart] = entry.betrag
    }
    if (Object.keys(prefill).length > 0) setHausgeldJeBa(prefill)
    // BA_ZEILEN hängt an den Abrechnungsarten des Objekts — die können nach
    // dem EV eintreffen, deshalb muss die Vorbelegung darauf erneut laufen.
  }, [aktivesEv, BA_ZEILEN])

  // Ohne positiven Betrag erhält der Käufer keine Sollstellungen — und zwar
  // dauerhaft, weil auch die HausgeldHistorie leer bleibt. Der Wechsel darf
  // hier nicht weiterlaufen, ohne dass das auffällt.
  const summe = BA_ZEILEN.reduce(
    (s, row) => s + (parseFloat(hausgeldJeBa[row.kontoart] ?? '') || 0),
    0,
  )
  const keinSoll = summe <= 0

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (keinSoll) return
    await onWeiter({ hausgeld_je_ba: hausgeldJeBa })
  }

  // Collect all unique future dates across all BAs for header columns
  const futureDates = Array.from(new Set(
    BA_ZEILEN.flatMap(row => getFutureEntries(eintraege, row.kontoart, today).map(h => h.gueltig_ab))
  )).sort()

  const hasFuture = futureDates.length > 0

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <p className="text-sm text-gray-500">
        Hausgeld-Sollbeträge für den Käufer festlegen.
        {wirkungsDatum && (
          <> Vorausgefüllt mit den Werten gültig zum <strong>{fmtDate(wirkungsDatum)}</strong>
          {hasFuture && <span className="text-amber-600"> — zukünftige Beschlüsse berücksichtigt</span>}
          .</>
        )}
      </p>

      {hasFuture && (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
          Achtung: Es liegen bereits Wirtschaftsplan-Beschlüsse für zukünftige Perioden vor.
          Die Käufer-Sollwerte wurden mit dem zum Wirkungsdatum gültigen Betrag vorausgefüllt.
        </div>
      )}

      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-24">BA</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Bezeichnung</th>
              <th className="text-right px-4 py-2.5 font-medium text-gray-600">Aktuell</th>
              {futureDates.map(d => (
                <th key={d} className="text-right px-4 py-2.5 font-medium text-amber-700 whitespace-nowrap">
                  ab {fmtDate(d)}
                </th>
              ))}
              <th className="text-right px-4 py-2.5 font-medium text-gray-800">Käufer-Soll</th>
            </tr>
          </thead>
          <tbody>
            {BA_ZEILEN.map(row => {
              const current = getEntryAt(eintraege, row.kontoart, today)
              const futureByDate: Record<string, HausgeldHistorie | undefined> = {}
              for (const d of futureDates) {
                futureByDate[d] = getFutureEntries(eintraege, row.kontoart, today).find(h => h.gueltig_ab === d)
              }
              return (
                <tr key={row.kontoart} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 font-mono text-gray-500">{row.kontoart}</td>
                  <td className="px-4 py-3 text-gray-700">{row.bezeichnung}</td>
                  <td className="px-4 py-3 text-right text-gray-500">
                    {current ? `${parseFloat(current.betrag).toFixed(2)} €` : '–'}
                  </td>
                  {futureDates.map(d => (
                    <td key={d} className="px-4 py-3 text-right text-amber-700">
                      {futureByDate[d] ? `${parseFloat(futureByDate[d]!.betrag).toFixed(2)} €` : '–'}
                    </td>
                  ))}
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="w-28 rounded border border-gray-300 px-2 py-1 text-sm text-right"
                      value={hausgeldJeBa[row.kontoart] ?? ''}
                      onChange={e => setHausgeldJeBa(prev => ({ ...prev, [row.kontoart]: e.target.value }))}
                      placeholder="0.00"
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {!aktivesEv && einheitId && (
        <p className="text-sm text-amber-600">Verkäufer-Daten werden geladen…</p>
      )}
      {aktivesEv && eintraege.length === 0 && (
        <p className="text-sm text-amber-600">Keine Hausgeld-Historie beim Verkäufer gefunden — bitte Beträge manuell eingeben.</p>
      )}
      {aktivesEv && eintraege.length > 0 && keinSoll && (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
          Keine Vorbelegung möglich: der Verkäufer hat für den{' '}
          {wirkungsDatum ? <>Stand <strong>{fmtDate(wirkungsDatum)}</strong></> : 'gewählten Stand'}{' '}
          keinen Hausgeld-Eintrag — seine Historie beginnt erst später. Bitte die
          Beträge manuell eintragen; ohne Soll erhält der Käufer keine
          Sollstellungen.
        </div>
      )}

      {errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 space-y-1">
          {errors.map((err, i) => <p key={i} className="text-sm text-red-600">{err}</p>)}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button type="submit" disabled={isLoading || keinSoll}>
          {isLoading ? 'Speichern…' : 'Weiter'}
        </Button>
      </div>
    </form>
  )
}
